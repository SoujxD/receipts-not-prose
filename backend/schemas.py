import re
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    computed_field,
    model_validator,
)

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

# ASSUMPTION: a newly submitted form has status None ("Unset"). The README allows
# None, 1, 2 or 3, and None is not treated as a synonym for 1 ("TO DO").
STATUS_LABELS: dict[Optional[int], str] = {
    None: "Unset",
    1: "TO DO",
    2: "IN PROGRESS",
    3: "COMPLETED",
}

# StrictInt is deliberate: Python's bool is an int subclass, and lax Pydantic
# would otherwise accept "2" or 2.0. Only the JSON integers 1, 2, 3 (or null) pass.
StatusValue = Annotated[
    StrictInt,
    Field(ge=1, le=3, description="1 = TO DO, 2 = IN PROGRESS, 3 = COMPLETED"),
]

# ---------------------------------------------------------------------------
# Contact fields (shared by REST bodies and tool arguments)
# ---------------------------------------------------------------------------


def _validate_email(value: str) -> str:
    try:
        # No DNS lookup: validation must work offline and in tests.
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


# ASSUMPTION: phone validation is intentionally modest and international-friendly:
# an optional leading "+", then digits with spaces, dashes, dots or parentheses,
# containing 7-15 digits (the E.164 maximum). The value is stored as entered.
_PHONE_CHARS = re.compile(r"^\+?[0-9 ().\-]+$")


def _validate_phone(value: str) -> str:
    digits = sum(ch.isdigit() for ch in value)
    if not _PHONE_CHARS.match(value) or not 7 <= digits <= 15:
        raise ValueError(
            "phone number must contain 7-15 digits and only digits, spaces, "
            "+ ( ) . or -"
        )
    return value


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=254),
    AfterValidator(_validate_email),
]
Phone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    AfterValidator(_validate_phone),
]
FormId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]

CONTACT_FIELDS = ("name", "email", "phone_number")

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class Chat(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    messages: list


class UserMessage(BaseModel):
    """The only message shape a client may author."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ChatCreate(BaseModel):
    # Clients may seed a chat with user messages only; assistant/tool/system
    # messages are authored by the server.
    messages: list[UserMessage] = []


class ChatUpdate(BaseModel):
    # Kept compatible with the starter frontend, which sends the full transcript.
    # The server only accepts it if it equals the stored transcript plus exactly
    # one new user message (see main.update_chat).
    messages: list[dict[str, Any]] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Form submissions
# ---------------------------------------------------------------------------


class FormSubmission(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: str
    created_at: datetime
    name: str
    phone_number: str
    email: str
    status: Optional[int] = None

    @computed_field  # type: ignore[misc]
    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, "Unknown")


class FormFields(BaseModel):
    """Contact details collected from the user. chat_id is never client-supplied."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    email: Email
    phone_number: Phone


class FormSubmissionCreate(BaseModel):
    """Internal create payload for crud.form.create (chat_id comes from the route)."""

    name: str
    phone_number: str
    email: str
    chat_id: str
    status: Optional[StatusValue] = None


class FormSubmissionUpdate(BaseModel):
    """Partial update. Omitted fields are left unchanged.

    - name / email / phone_number: when supplied, must be valid and non-blank;
      explicit null is rejected.
    - status: omitted = unchanged, null = clear to Unset, 1/2/3 = set.
    - id, chat_id, created_at and unknown fields are rejected (extra="forbid").
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"phone_number": "+1 415 555 0199", "status": 2}, {"status": None}]},
    )

    # Defaults are not validated by Pydantic, so None here means "omitted".
    name: Name = None  # type: ignore[assignment]
    email: Email = None  # type: ignore[assignment]
    phone_number: Phone = None  # type: ignore[assignment]
    status: Optional[StatusValue] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_null_contact_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            nulls = [f for f in CONTACT_FIELDS if f in data and data[f] is None]
            if nulls:
                raise ValueError(
                    f"{', '.join(nulls)} cannot be null; omit a field to leave it unchanged"
                )
        return data

    def requested_changes(self) -> dict[str, Any]:
        # Presence-aware: keeps an explicit {"status": null}; never use exclude_none here.
        return self.model_dump(exclude_unset=True)


# ---------------------------------------------------------------------------
# Tool arguments (validated before any write)
# ---------------------------------------------------------------------------


class SubmitFormArgs(FormFields):
    pass


class ListFormsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpdateFormArgs(FormSubmissionUpdate):
    form_id: FormId

    def to_update(self) -> FormSubmissionUpdate:
        return FormSubmissionUpdate.model_validate(
            self.model_dump(exclude_unset=True, exclude={"form_id"})
        )


class DeleteFormArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form_id: FormId
