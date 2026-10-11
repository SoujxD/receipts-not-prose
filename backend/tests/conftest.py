"""Test fixtures: a freshly migrated temporary SQLite database and a scripted fake model.

Nothing here talks to OpenAI. Routes, validation, CRUD and the database are real; only
the model client is replaced (injected through FastAPI's dependency overrides).
"""

import itertools
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Guarantee no real credentials are picked up from backend/.env during tests
# (load_dotenv never overrides a variable that is already set).
os.environ["OPENAI_API_KEY"] = ""

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall  # noqa: E402
from openai.types.chat.chat_completion_message_tool_call import Function  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import main  # noqa: E402

_call_ids = itertools.count(1)


def reply(text: str) -> ChatCompletionMessage:
    return ChatCompletionMessage(role="assistant", content=text)


def tool_calls(*calls) -> ChatCompletionMessage:
    """calls: (tool_name, args) where args is a dict (JSON-encoded) or a raw string."""
    return ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[
            ChatCompletionMessageToolCall(
                id=f"call_{next(_call_ids)}",
                type="function",
                function=Function(name=name, arguments=args if isinstance(args, str) else json.dumps(args)),
            )
            for name, args in calls
        ],
    )


class FakeModel:
    """Mimics client.chat.completions.create, returning scripted responses in order."""

    def __init__(self):
        self.script: list = []
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def queue(self, *steps):
        self.script.extend(steps)

    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        assert self.script, "unexpected extra model call"
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return SimpleNamespace(choices=[SimpleNamespace(message=step)])


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{path.as_posix()}")
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")  # also proves the migration builds the schema
    return path


@pytest.fixture
def model():
    return FakeModel()


@pytest.fixture
def client(db_path, model):
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", poolclass=NullPool)
    Session = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)

    async def override_db():
        async with Session() as session:
            yield session

    main.app.dependency_overrides[main.get_db] = override_db
    main.app.dependency_overrides[main.get_model_client] = lambda: model
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


@pytest.fixture
def new_chat(client):
    return lambda: client.post("/chat", json={}).json()["id"]


@pytest.fixture
def chat_id(new_chat):
    return new_chat()


@pytest.fixture
def say(client):
    """Send one user message the way the frontend does: stored transcript + new message."""

    def _say(chat_id: str, text: str):
        stored = client.get(f"/chat/{chat_id}").json()["messages"]
        return client.put(f"/chat/{chat_id}", json={"messages": stored + [{"role": "user", "content": text}]})

    return _say


@pytest.fixture
def seed(model, say, client):
    """Create forms through the real submit_interest_form tool path; returns the saved forms."""

    def _seed(chat_id: str, *people: dict):
        model.queue(tool_calls(*[("submit_interest_form", p) for p in people]), reply("Saved."))
        assert say(chat_id, "please submit these").status_code == 200
        return client.get(f"/chat/{chat_id}/forms").json()

    return _seed


@pytest.fixture
def rows(db_path):
    """Read form rows straight from SQLite, independent of the app's code."""

    def _rows(chat_id: str | None = None):
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        sql = "SELECT id, chat_id, name, email, phone_number, status FROM form_submission"
        args: tuple = ()
        if chat_id:
            sql, args = sql + " WHERE chat_id = ?", (chat_id,)
        out = [dict(r) for r in con.execute(sql + " ORDER BY created_at, id", args)]
        con.close()
        return out

    return _rows


def tool_results(chat: dict) -> list[dict]:
    return [json.loads(m["content"]) for m in chat["messages"] if m["role"] == "tool"]


ADA = {"name": "Ada Lovelace", "email": "ada@example.com", "phone_number": "+44 20 7946 0958"}
GRACE = {"name": "Grace Hopper", "email": "grace@example.com", "phone_number": "(555) 010-0199"}
