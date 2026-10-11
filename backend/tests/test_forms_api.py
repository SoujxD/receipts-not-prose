"""REST contract for /chat/{chat_id}/forms: status semantics, partial updates, filters, scoping."""

import pytest

from conftest import ADA, GRACE


@pytest.fixture
def form(chat_id, seed):
    return seed(chat_id, ADA)[0]


def patch(client, form, body):
    return client.patch(f"/chat/{form['chat_id']}/forms/{form['id']}", json=body)


# --- status -----------------------------------------------------------------


@pytest.mark.parametrize("value, label", [(1, "TO DO"), (2, "IN PROGRESS"), (3, "COMPLETED"), (None, "Unset")])
def test_allowed_statuses_round_trip(client, form, rows, value, label):
    if value is None:
        assert patch(client, form, {"status": 2}).status_code == 200
    resp = patch(client, form, {"status": value})
    assert resp.status_code == 200
    assert (resp.json()["status"], resp.json()["status_label"]) == (value, label)
    assert rows()[0]["status"] == value
    assert client.get(f"/chat/{form['chat_id']}/forms").json()[0]["status"] == value


@pytest.mark.parametrize("bad", [0, 4, -1, "1", "TO DO", True, False, 1.5, 2.0, [1], {}])
def test_invalid_status_rejected_without_write(client, form, rows, bad):
    before = rows()
    assert patch(client, form, {"status": bad, "name": "Changed"}).status_code == 422
    assert rows() == before


def test_new_forms_default_to_unset(form):
    assert form["status"] is None and form["status_label"] == "Unset"


# --- partial update ------------------------------------------------------------


def test_one_field_patch_preserves_everything_else(client, form, rows):
    assert patch(client, form, {"status": 2}).status_code == 200
    resp = patch(client, form, {"phone_number": "+1 415 555 0123"})
    assert resp.status_code == 200
    saved = rows()[0]
    assert saved["phone_number"] == "+1 415 555 0123"
    assert saved["status"] == 2  # omitted status is preserved
    assert (saved["name"], saved["email"]) == (ADA["name"], ADA["email"])


def test_explicit_null_clears_status(client, form, rows):
    patch(client, form, {"status": 3})
    resp = patch(client, form, {"status": None})
    assert resp.status_code == 200 and resp.json()["status"] is None
    assert rows()[0]["status"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"name": "   "},
        {"name": None},
        {"email": None},
        {"phone_number": None},
        {"email": "not-an-email"},
        {"phone_number": "call me"},
        {"phone_number": "12"},
        {"id": "other"},
        {"chat_id": "other"},
        {"created_at": "2024-01-01T00:00:00"},
        {"nickname": "Ada"},
    ],
)
def test_invalid_or_forbidden_fields_rejected(client, form, rows, body):
    before = rows()
    assert patch(client, form, body).status_code == 422
    assert rows() == before


def test_contact_fields_are_trimmed_and_international_phone_accepted(client, form):
    resp = patch(client, form, {"name": "  Ada King  ", "phone_number": "+91 98765-43210"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Ada King"
    assert resp.json()["phone_number"] == "+91 98765-43210"


@pytest.mark.parametrize("body", [{}, {"name": ADA["name"], "status": None}])
def test_empty_or_unchanged_patch_is_noop(client, form, rows, body):
    before = rows()
    resp = patch(client, form, body)
    assert resp.status_code == 200
    assert resp.json() == form
    assert rows() == before


# --- listing -------------------------------------------------------------------


def test_list_filters_by_chat_and_status(client, new_chat, seed):
    chat_a, chat_b, chat_empty = new_chat(), new_chat(), new_chat()
    a_forms = seed(chat_a, ADA, GRACE)
    seed(chat_b, ADA)
    patch(client, a_forms[1], {"status": 2})

    def ids(query=""):
        resp = client.get(f"/chat/{chat_a}/forms{query}")
        assert resp.status_code == 200
        return [f["id"] for f in resp.json()]

    assert ids() == [a_forms[0]["id"], a_forms[1]["id"]]
    assert ids("?status=2") == [a_forms[1]["id"]]
    assert ids("?status=null") == [a_forms[0]["id"]]
    assert ids("?status=1") == []
    assert client.get(f"/chat/{chat_empty}/forms").json() == []


@pytest.mark.parametrize("query", ["0", "4", "abc", "", "None", "1.0", "true"])
def test_invalid_status_query_is_422(client, chat_id, query):
    assert client.get(f"/chat/{chat_id}/forms", params={"status": query}).status_code == 422


def test_list_is_not_truncated_at_100(client, chat_id, seed):
    people = [{**ADA, "name": f"Person {i}"} for i in range(105)]
    assert len(seed(chat_id, *people)) == 105


# --- scoping and 404s ------------------------------------------------------------


def test_unknown_chat_is_404(client):
    assert client.get("/chat/nope").status_code == 404
    assert client.get("/chat/nope/forms").status_code == 404
    assert client.patch("/chat/nope/forms/x", json={"status": 1}).status_code == 404
    assert client.delete("/chat/nope/forms/x").status_code == 404


def test_cannot_read_or_mutate_another_chats_form(client, new_chat, form, rows):
    other = new_chat()
    assert client.patch(f"/chat/{other}/forms/{form['id']}", json={"status": 1}).status_code == 404
    assert client.delete(f"/chat/{other}/forms/{form['id']}").status_code == 404
    assert client.get(f"/chat/{other}/forms").json() == []
    assert rows()[0]["status"] is None  # untouched


def test_delete_returns_204_and_removes_row(client, form, rows):
    resp = client.delete(f"/chat/{form['chat_id']}/forms/{form['id']}")
    assert resp.status_code == 204 and resp.content == b""
    assert rows() == []
    assert client.delete(f"/chat/{form['chat_id']}/forms/{form['id']}").status_code == 404
