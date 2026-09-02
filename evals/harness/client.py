"""The running service as a black box (rag-evaluation spec, *Both strategies are evaluated
through the running service*). Nothing here imports application code."""

import calendar
import datetime as dt
import secrets
import time

import httpx

Strategy = str  # "basic" | "advanced"


class ServiceUnavailable(RuntimeError):
    pass


def birth_date_for(months: int, as_of: dt.date) -> dt.date:
    """The latest date of birth that gives exactly ``months`` completed months on ``as_of``.

    The cases describe children in months (hard rule 1); the API takes a date of birth and
    derives the age. Mirrors ``backend.nutrition.age.birth_date_for`` without importing it.
    """
    year, month = divmod(as_of.year * 12 + (as_of.month - 1) - months, 12)
    return dt.date(year, month + 1, min(as_of.day, calendar.monthrange(year, month + 1)[1]))


class ServiceClient:
    def __init__(self, base_url: str, timeout: float = 240.0) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=timeout)
        self.account: dict | None = None

    # -- health ---------------------------------------------------------------------------

    def health(self) -> dict:
        return self.http.get("/health").json()

    def require_database(self) -> None:
        """Registering the run's account (and saving chat cases' children) needs the database."""
        status = self.health()
        if status.get("database") != "reachable":
            raise ServiceUnavailable(f"database is {status.get('database')!r}; chat cases need it")

    # -- knowledge base -------------------------------------------------------------------

    def ask(self, question: str, strategy: Strategy) -> tuple[dict, int]:
        started = time.perf_counter()
        response = self.http.post(
            "/api/ask", json={"question": question, "strategy": strategy, "stream": False}
        )
        response.raise_for_status()
        return response.json(), int((time.perf_counter() - started) * 1000)

    # -- account and children (throwaway, per run) ----------------------------------------

    def register(self) -> dict:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
        credentials = {
            "email": f"eval+{stamp}-{secrets.token_hex(3)}@example.com",
            "password": secrets.token_urlsafe(18),
        }
        response = self.http.post("/api/auth/register", json=credentials)
        response.raise_for_status()
        self.account = response.json()
        return self.account

    def save_child(self, child: dict) -> dict:
        body = dict(child)
        if "age_months" in body:
            as_of = dt.datetime.now(dt.UTC).date()
            body["birth_date"] = birth_date_for(body.pop("age_months"), as_of).isoformat()
        response = self.http.post("/api/children", json=body)
        response.raise_for_status()
        return response.json()

    def delete_child(self, child_id: str) -> None:
        self.http.delete(f"/api/children/{child_id}").raise_for_status()

    def log_feeds(self, child_id: str, entries: list[dict]) -> None:
        for entry in entries:
            response = self.http.post(f"/api/children/{child_id}/feedings", json=entry)
            response.raise_for_status()

    def chat(self, message: str, child_id: str | None, strategy: Strategy) -> tuple[dict, int]:
        body: dict = {"message": message, "strategy": strategy, "stream": False}
        if child_id is not None:
            body["child_id"] = child_id
        started = time.perf_counter()
        response = self.http.post("/api/chat", json=body)
        response.raise_for_status()
        return response.json(), int((time.perf_counter() - started) * 1000)
