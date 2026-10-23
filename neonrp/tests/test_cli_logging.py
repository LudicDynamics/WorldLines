"""Tests for CLI logging setup behavior."""

from __future__ import annotations

import logging
from pathlib import Path

from neonrp.cli import _setup_logging


def _handler_path(handler: logging.Handler) -> Path | None:
    base = getattr(handler, "baseFilename", "")
    if not isinstance(base, str) or not base:
        return None
    return Path(base).resolve()


def _file_handlers_for(path: Path) -> list[logging.Handler]:
    logger = logging.getLogger("neonrp")
    target = path.resolve()
    handlers: list[logging.Handler] = []
    for handler in logger.handlers:
        resolved = _handler_path(handler)
        if resolved is not None and resolved == target:
            handlers.append(handler)
    return handlers


def _remove_file_handlers_for(path: Path) -> None:
    logger = logging.getLogger("neonrp")
    for handler in list(_file_handlers_for(path)):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def _file_handlers_for_logger(logger_name: str, path: Path) -> list[logging.Handler]:
    logger = logging.getLogger(logger_name)
    target = path.resolve()
    handlers: list[logging.Handler] = []
    for handler in logger.handlers:
        resolved = _handler_path(handler)
        if resolved is not None and resolved == target:
            handlers.append(handler)
    return handlers


def _remove_file_handlers_for_logger(logger_name: str, path: Path) -> None:
    logger = logging.getLogger(logger_name)
    for handler in list(_file_handlers_for_logger(logger_name, path)):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def test_setup_logging_is_idempotent_for_same_project_log(tmp_path: Path) -> None:
    log_file = tmp_path / ".neonrp" / "logs" / "neonrp.log"
    _remove_file_handlers_for(log_file)

    _setup_logging(tmp_path)
    _setup_logging(tmp_path)
    _setup_logging(tmp_path)

    handlers = _file_handlers_for(log_file)
    assert len(handlers) == 1

    # Cleanup to avoid leaking open handlers across test process.
    _remove_file_handlers_for(log_file)


def test_setup_logging_adds_idempotent_raw_json_handler(tmp_path: Path) -> None:
    raw_log_file = tmp_path / ".neonrp" / "logs" / "llm_raw.jsonl"
    _remove_file_handlers_for_logger("neonrp.raw_json", raw_log_file)

    _setup_logging(tmp_path)
    _setup_logging(tmp_path)
    _setup_logging(tmp_path)

    handlers = _file_handlers_for_logger("neonrp.raw_json", raw_log_file)
    assert len(handlers) == 1

    _remove_file_handlers_for_logger("neonrp.raw_json", raw_log_file)
