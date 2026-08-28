"""Password hashing and session tokens without HTTP or a database."""

import datetime as dt
import uuid

import jwt
import pytest

from backend.auth.passwords import hash_password, verify_password
from backend.auth.tokens import issue_session_token, read_session_token

SECRET = "x" * 32


class TestPasswords:
    def test_hash_is_not_the_password_and_verifies(self) -> None:
        hashed = hash_password("correct horse battery")
        assert "correct horse" not in hashed
        assert hashed.startswith("$argon2id$")
        assert verify_password(hashed, "correct horse battery")

    def test_wrong_password_is_rejected(self) -> None:
        assert not verify_password(hash_password("right"), "wrong")

    def test_same_password_hashes_differently(self) -> None:
        assert hash_password("same") != hash_password("same")

    def test_hash_fits_the_column(self) -> None:
        assert len(hash_password("p" * 128)) <= 255

    def test_missing_hash_is_false_not_an_error(self) -> None:
        assert verify_password(None, "anything") is False

    def test_garbage_hash_is_false_not_an_error(self) -> None:
        assert verify_password("not-a-hash", "anything") is False


class TestSessionTokens:
    def test_round_trip(self) -> None:
        user_id = uuid.uuid7()
        token = issue_session_token(user_id, SECRET, dt.timedelta(hours=1))
        assert read_session_token(token, SECRET) == user_id

    def test_wrong_secret_is_rejected(self) -> None:
        token = issue_session_token(uuid.uuid7(), SECRET, dt.timedelta(hours=1))
        assert read_session_token(token, "y" * 32) is None

    def test_expired_token_is_rejected(self) -> None:
        token = issue_session_token(uuid.uuid7(), SECRET, dt.timedelta(seconds=-1))
        assert read_session_token(token, SECRET) is None

    @pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
    def test_malformed_token_is_rejected(self, token: str) -> None:
        assert read_session_token(token, SECRET) is None

    def test_token_without_expiry_is_rejected(self) -> None:
        token = jwt.encode({"sub": str(uuid.uuid7())}, SECRET, algorithm="HS256")
        assert read_session_token(token, SECRET) is None

    def test_token_with_non_uuid_subject_is_rejected(self) -> None:
        now = dt.datetime.now(dt.UTC)
        token = jwt.encode(
            {"sub": "admin", "exp": now + dt.timedelta(hours=1)}, SECRET, algorithm="HS256"
        )
        assert read_session_token(token, SECRET) is None
