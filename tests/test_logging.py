"""Request context and structured logging (observability spec)."""

import asyncio
import datetime as dt
import json
import logging
import sys
import uuid

import pytest

from backend.core import request_context as ctx
from backend.core.config import Settings
from backend.core.logging import JsonFormatter, RequestContextFilter, configure_logging

DEV = "postgresql+asyncpg://u:p@h/nutrition"


class TestRequestContext:
    async def test_values_flow_into_awaited_coroutines(self) -> None:
        async def inner() -> tuple[str | None, str | None, str | None]:
            return ctx.get_request_id(), ctx.get_user_id(), ctx.get_child_profile_id()

        user = uuid.uuid7()
        ctx.set_request_id("req-1")
        ctx.set_user_id(user)
        ctx.set_child_profile_id(None)
        try:
            assert await inner() == ("req-1", str(user), None)
        finally:
            ctx.reset_request_context()
        assert await inner() == (None, None, None)

    async def test_values_do_not_leak_between_tasks(self) -> None:
        async def set_and_read(value: str) -> str | None:
            ctx.set_request_id(value)
            await asyncio.sleep(0)
            return ctx.get_request_id()

        results = await asyncio.gather(set_and_read("a"), set_and_read("b"))
        assert results == ["a", "b"]
        assert ctx.get_request_id() is None


DEV = "postgresql+asyncpg://u:p@h/nutrition"


def _record(**extra) -> logging.LogRecord:
    record = logging.getLogger("backend.test").makeRecord(
        "backend.test", logging.INFO, __file__, 1, "hello %s", ("world",), None, extra=extra
    )
    RequestContextFilter().filter(record)
    return record


class TestJsonFormatter:
    def test_line_is_json_with_fixed_and_context_keys(self) -> None:
        ctx.set_request_id("req-9")
        ctx.set_user_id("u-1")
        try:
            line = JsonFormatter().format(_record())
        finally:
            ctx.reset_request_context()
        payload = json.loads(line)
        assert payload["message"] == "hello world"
        assert payload["level"] == "INFO" and payload["logger"] == "backend.test"
        assert payload["ts"].endswith("+00:00")
        assert payload["request_id"] == "req-9" and payload["user_id"] == "u-1"
        assert payload["child_profile_id"] is None
        assert "\n" not in line

    def test_extra_fields_are_included_and_reserved_ones_are_not(self) -> None:
        payload = json.loads(JsonFormatter().format(_record(tool="calculate_bmi", latency_ms=3)))
        assert payload["tool"] == "calculate_bmi" and payload["latency_ms"] == 3
        for reserved in ("args", "msg", "levelno", "pathname", "created"):
            assert reserved not in payload

    def test_exception_records_carry_the_traceback(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.getLogger("backend.test").makeRecord(
                "backend.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
            )
        RequestContextFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
        assert "ValueError: boom" in payload["exc_info"] and "Traceback" in payload["exc_info"]

    def test_non_serialisable_extra_is_stringified(self) -> None:
        payload = json.loads(JsonFormatter().format(_record(when=dt.datetime.now(dt.UTC))))
        assert isinstance(payload["when"], str)


@pytest.fixture
def restore_logging():
    """Put the root logger and the audit logger back the way pytest found them."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    audit = logging.getLogger("backend.tools.audit")
    saved_audit = (list(audit.handlers), audit.propagate)
    yield
    for h in list(root.handlers):
        if h not in saved[0]:
            root.removeHandler(h)
            h.close()
    for h in saved[0]:
        if h not in root.handlers:
            root.addHandler(h)
    root.setLevel(saved[1])
    for h in list(audit.handlers):
        audit.removeHandler(h)
        h.close()
    for h in saved_audit[0]:
        audit.addHandler(h)
    audit.propagate = saved_audit[1]


class TestConfigureLogging:
    def test_installs_exactly_one_root_handler_and_is_idempotent(self, restore_logging) -> None:
        settings = Settings(database_url=DEV, log_format="json", _env_file=None)
        configure_logging(settings)
        configure_logging(settings)
        root = logging.getLogger()
        ours = [h for h in root.handlers if getattr(h, "_nutrition_app_handler", False)]
        assert len(ours) == 1
        assert isinstance(ours[0].formatter, JsonFormatter)
        assert root.level == logging.INFO

    def test_text_format_and_level(self, restore_logging, capsys) -> None:
        configure_logging(
            Settings(database_url=DEV, log_format="text", log_level="WARNING", _env_file=None)
        )
        logging.getLogger("backend.test").info("quiet")
        logging.getLogger("backend.test").warning("loud")
        out = capsys.readouterr().out
        assert "quiet" not in out and "loud" in out
        assert "WARNING  backend.test [None]: loud" in out

    def test_defaults_without_settings(self, restore_logging) -> None:
        configure_logging(None)
        root = logging.getLogger()
        [ours] = [h for h in root.handlers if getattr(h, "_nutrition_app_handler", False)]
        assert isinstance(ours.formatter, JsonFormatter) and root.level == logging.INFO

    def test_audit_file_receives_audit_records_exactly_once(
        self, restore_logging, tmp_path, capsys
    ) -> None:
        path = tmp_path / "audit.jsonl"
        configure_logging(
            Settings(database_url=DEV, log_format="json", audit_log_path=str(path), _env_file=None)
        )
        ctx.set_request_id("req-audit")
        try:
            logging.getLogger("backend.tools.audit").info("meal_plan_audit %s", '{"event": "x"}')
        finally:
            ctx.reset_request_context()
        for handler in logging.getLogger("backend.tools.audit").handlers:
            handler.flush()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["message"] == 'meal_plan_audit {"event": "x"}'
        assert record["request_id"] == "req-audit"
        assert "meal_plan_audit" not in capsys.readouterr().out

    def test_without_audit_path_audit_records_reach_the_main_log(
        self, restore_logging, capsys
    ) -> None:
        configure_logging(Settings(database_url=DEV, log_format="json", _env_file=None))
        logging.getLogger("backend.tools.audit").info("nutrient_gaps_audit {}")
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert payload["message"] == "nutrient_gaps_audit {}"
        assert logging.getLogger("backend.tools.audit").propagate is True


class TestEngineNeverEchoes:
    def test_sql_echo_is_off_in_every_environment(self, monkeypatch) -> None:
        """SQL echo prints bound parameters -- emails and password hashes -- so it stays off."""
        from backend.core.config import get_settings
        from backend.db.session import get_engine, reset_engine_cache

        monkeypatch.setenv("DATABASE_URL", DEV)
        monkeypatch.setenv("APP_ENV", "dev")
        get_settings.cache_clear()
        reset_engine_cache()
        try:
            assert get_engine().echo is False
        finally:
            reset_engine_cache()
            get_settings.cache_clear()
