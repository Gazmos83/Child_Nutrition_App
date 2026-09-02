"""Request and response models for ``/api/auth`` (authentication spec)."""

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.auth.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from backend.models.user import EMAIL_MAX_LENGTH


class Credentials(BaseModel):
    """Email and password, for both registration and sign-in."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=EMAIL_MAX_LENGTH)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class CurrentUserResponse(BaseModel):
    """Who the session belongs to. Never carries the hash or the token."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    email: str
    is_admin: bool = Field(
        default=False, description="Listed in ADMIN_EMAILS; may edit the food table."
    )
