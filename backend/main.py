import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

import agent
import crud
import forms
import schemas
from database import SessionLocal

# The API key lives in backend/.env (see .env.example), not in source code.
load_dotenv(Path(__file__).with_name(".env"))

DEFAULT_MODEL = "gpt-4o-mini"

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Aurelian interest-form chat",
    description=(
        "Chat with an assistant that can submit, list, update and delete interest forms. "
        "Form status: null = Unset, 1 = TO DO, 2 = IN PROGRESS, 3 = COMPLETED."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(forms.ChatNotFound)
async def chat_not_found_handler(request: Request, exc: forms.ChatNotFound):
    return JSONResponse(status_code=404, content={"detail": "Chat not found"})


@app.exception_handler(forms.FormNotFound)
async def form_not_found_handler(request: Request, exc: forms.FormNotFound):
    return JSONResponse(status_code=404, content={"detail": "Form not found in this chat"})


@app.exception_handler(forms.FormWriteError)
async def form_write_error_handler(request: Request, exc: forms.FormWriteError):
    return JSONResponse(status_code=503, content={"detail": f"{exc} No changes were saved."})


# Get a DB Session
async def get_db() -> AsyncGenerator:
    async with SessionLocal() as session:
        yield session


@lru_cache
def _openai_client(api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=1)


def get_model_client() -> Optional[AsyncOpenAI]:
    """Returns None when no key is configured. REST routes and tests never need one."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return _openai_client(api_key) if api_key else None


def get_model_name() -> str:
    return os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_MODEL


@app.get("/")
async def root():
    return {"message": "Hello World"}

# response_model represents the format of the response that this endpoint will produce. Responses are always in JSON
@app.get("/chat", response_model=list[schemas.Chat], summary="List the 10 most recent chats")
async def get_chats(db: AsyncSession = Depends(get_db)):
    chats = await crud.chat.get_recent(db, limit=10)
    return chats

# the data parameter represents the body of the request. The request body should always be in JSON format
@app.post("/chat", response_model=schemas.Chat, summary="Create a chat")
async def create_chat(data: schemas.ChatCreate, db: AsyncSession = Depends(get_db)):
    chat = await crud.chat.create(db=db, obj_in=data)
    return chat


def _new_user_message(stored: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> dict[str, Any]:
    """Accept the starter's full-transcript payload only if it is the stored transcript
    plus exactly one new user message. The server's stored copy is what gets used, so a
    client cannot inject or rewrite assistant/tool/system messages."""
    *prefix, last = incoming
    try:
        user = schemas.UserMessage.model_validate(last)
    except ValidationError:
        raise HTTPException(
            status_code=422,
            detail="The last message must be a single non-empty user message: {\"role\": \"user\", \"content\": \"...\"}.",
        )
    if prefix != stored:
        raise HTTPException(
            status_code=409,
            detail="This chat changed since it was loaded, or the history was modified. Reload the chat and try again.",
        )
    return user.model_dump()


# the chat_id parameter maps to the chat id in the URL
@app.put(
    "/chat/{chat_id}",
    response_model=schemas.Chat,
    summary="Send one user message and get the assistant's reply",
    responses={
        404: {"description": "Chat not found"},
        409: {"description": "Submitted history does not match the stored chat (stale or modified)"},
        503: {"description": "Model not configured or unavailable; nothing was saved"},
    },
)
async def update_chat(
    chat_id: str,
    data: schemas.ChatUpdate,
    db: AsyncSession = Depends(get_db),
    client: Optional[Any] = Depends(get_model_client),
):
    chat = await forms.get_chat_or_raise(db, chat_id)
    stored = list(chat.messages or [])
    user_message = _new_user_message(stored, data.messages)

    if client is None:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured on the backend (see backend/.env.example). Nothing was saved.",
        )

    async def persist(messages: list[dict[str, Any]]) -> None:
        # Re-load the chat: a rolled-back form write expires objects in the session.
        current = await forms.get_chat_or_raise(db, chat_id)
        await crud.chat.update(db, db_obj=current, obj_in={"messages": list(messages)})

    try:
        await agent.run_chat_turn(
            db, chat_id, stored + [user_message], client, get_model_name(), persist
        )
    except agent.ModelUnavailable:
        raise HTTPException(
            status_code=503,
            detail="The assistant is temporarily unavailable. Your message was not processed and nothing was saved.",
        )

    return await forms.get_chat_or_raise(db, chat_id)


@app.get(
    "/chat/{chat_id}",
    response_model=schemas.Chat,
    responses={404: {"description": "Chat not found"}},
)
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    chat = await forms.get_chat_or_raise(db, chat_id)

    return chat


# ---------------------------------------------------------------------------
# Form submissions
# ---------------------------------------------------------------------------


@app.get(
    "/chat/{chat_id}/forms",
    response_model=list[schemas.FormSubmission],
    summary="List every form submitted in a chat",
    description="Ordered by creation time, then ID. Not paginated: all matching forms are returned.",
    responses={404: {"description": "Chat not found"}},
)
async def list_chat_forms(
    chat_id: str,
    status_filter: Optional[Literal["1", "2", "3", "null"]] = Query(
        None,
        alias="status",
        description='Omit for all forms. "1" TO DO, "2" IN PROGRESS, "3" COMPLETED, "null" Unset.',
    ),
    db: AsyncSession = Depends(get_db),
):
    return await forms.list_forms(db, chat_id, forms.parse_status_query(status_filter))


@app.patch(
    "/chat/{chat_id}/forms/{form_id}",
    response_model=schemas.FormSubmission,
    summary="Partially update a form",
    description=(
        "Only supplied fields change. Omitting `status` keeps it; `\"status\": null` clears it to Unset. "
        "An empty body is a no-op that returns the current form. name/email/phone_number cannot be null."
    ),
    responses={404: {"description": "Chat not found, or form not in this chat"}},
)
async def update_chat_form(
    chat_id: str,
    form_id: str,
    data: schemas.FormSubmissionUpdate,
    db: AsyncSession = Depends(get_db),
):
    form, _changes = await forms.update_form(db, chat_id, form_id, data)
    return form


@app.delete(
    "/chat/{chat_id}/forms/{form_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a form",
    responses={404: {"description": "Chat not found, or form not in this chat"}},
)
async def delete_chat_form(chat_id: str, form_id: str, db: AsyncSession = Depends(get_db)):
    await forms.delete_form(db, chat_id, form_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
