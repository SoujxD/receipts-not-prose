"""Form operations shared by the REST routes and the chat tools.

Both callers go through these functions, so validation (via the Pydantic schemas)
and chat scoping are enforced in one place.

Commit boundaries: each mutating function is its own unit of work. The supplied
CRUD helpers commit per operation; on a database error we roll back that one
operation and raise FormWriteError. Earlier operations in the same chat turn
have already committed and stay committed - callers must not claim otherwise.
"""

from typing import Any, Optional, Union

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

import crud
import schemas
from models import Chat, FormSubmission


class ChatNotFound(Exception):
    pass


class FormNotFound(Exception):
    pass


class FormWriteError(Exception):
    pass


class _AllStatuses:
    def __repr__(self) -> str:
        return "ALL_STATUSES"


# Sentinel: "no status filter". None is a real filter value meaning "Unset".
ALL_STATUSES = _AllStatuses()
StatusFilter = Union[_AllStatuses, None, int]


def snapshot(form: FormSubmission) -> dict[str, Any]:
    """JSON-safe copy of a saved form, used in tool results and receipts."""
    return schemas.FormSubmission.model_validate(form).model_dump(mode="json")


async def get_chat_or_raise(db: AsyncSession, chat_id: str) -> Chat:
    chat = await crud.chat.get(db, id=chat_id)
    if chat is None:
        raise ChatNotFound(chat_id)
    return chat


async def get_form_or_raise(db: AsyncSession, chat_id: str, form_id: str) -> FormSubmission:
    await get_chat_or_raise(db, chat_id)
    form = await crud.form.get_for_chat(db, chat_id=chat_id, form_id=form_id)
    if form is None:
        # Also covers a form that exists but belongs to another chat.
        raise FormNotFound(form_id)
    return form


async def list_forms(
    db: AsyncSession, chat_id: str, status: StatusFilter = ALL_STATUSES
) -> list[FormSubmission]:
    await get_chat_or_raise(db, chat_id)
    filters = []
    if status is None:
        filters.append(FormSubmission.status.is_(None))
    elif not isinstance(status, _AllStatuses):
        filters.append(FormSubmission.status == status)
    return list(await crud.form.list_for_chat(db, chat_id=chat_id, filters=filters))


async def create_form(db: AsyncSession, chat_id: str, fields: schemas.FormFields) -> FormSubmission:
    # Deliberately no de-duplication by name/email: two submissions with the same
    # contact details are two records.
    await get_chat_or_raise(db, chat_id)
    obj_in = schemas.FormSubmissionCreate(**fields.model_dump(), chat_id=chat_id, status=None)
    try:
        return await crud.form.create(db, obj_in=obj_in)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise FormWriteError("The form could not be saved.") from exc


async def update_form(
    db: AsyncSession, chat_id: str, form_id: str, patch: schemas.FormSubmissionUpdate
) -> tuple[FormSubmission, dict[str, dict[str, Any]]]:
    """Apply a partial update. Returns the saved form and the fields that actually changed.

    `changes` is computed from validated values before and after - never from model text.
    An empty patch, or one whose values equal the current ones, is a no-op: nothing is
    written and `changes` is empty.
    """
    form = await get_form_or_raise(db, chat_id, form_id)
    before = snapshot(form)
    changes = {
        field: {"from": before[field], "to": value}
        for field, value in patch.requested_changes().items()
        if before[field] != value
    }
    if not changes:
        return form, {}
    try:
        form = await crud.form.update(
            db, db_obj=form, obj_in={field: c["to"] for field, c in changes.items()}
        )
    except SQLAlchemyError as exc:
        await db.rollback()
        raise FormWriteError("The form could not be updated.") from exc
    return form, changes


async def delete_form(db: AsyncSession, chat_id: str, form_id: str) -> dict[str, Any]:
    """Delete a form and return a snapshot of what was deleted."""
    form = await get_form_or_raise(db, chat_id, form_id)
    deleted = snapshot(form)
    try:
        await crud.form.remove(db, id=form.id)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise FormWriteError("The form could not be deleted.") from exc
    return deleted


def parse_status_query(value: Optional[str]) -> StatusFilter:
    """Query strings arrive as text: omitted = all, "null" = Unset, "1"/"2"/"3" = that status.

    Anything else is rejected earlier by the route's Literal type (422).
    """
    if value is None:
        return ALL_STATUSES
    if value == "null":
        return None
    return int(value)
