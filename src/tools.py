"""Tool wrappers with guardrails and timeout support."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class ToolTimeoutError(RuntimeError):
    pass


class ToolValidationError(RuntimeError):
    pass


def run_with_timeout(func: Callable[..., Any], timeout_sec: int, *args: Any, **kwargs: Any) -> Any:
    result: dict[str, Any] = {"value": None, "error": None}

    def runner() -> None:
        try:
            result["value"] = func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        raise ToolTimeoutError(f"Tool call exceeded timeout of {timeout_sec}s")

    if result["error"] is not None:
        raise result["error"]

    return result["value"]


def validate_categorized_output(items: list[Any]) -> None:
    if not isinstance(items, list):
        raise ToolValidationError("Categorizer output must be a list")
    for item in items:
        if not hasattr(item, "category") or not isinstance(item.category, str) or not item.category:
            raise ToolValidationError("Each categorized transaction must have a non-empty category")


def validate_anomaly_output(items: list[Any]) -> None:
    if not isinstance(items, list):
        raise ToolValidationError("Anomaly output must be a list")
    for item in items:
        if not hasattr(item, "z_score") or float(item.z_score) < 0:
            raise ToolValidationError("Each anomaly must include a non-negative z_score")
