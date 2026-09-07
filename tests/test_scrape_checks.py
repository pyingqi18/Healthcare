"""Offline tests for DataForSEO diagnostic scripts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script(filename: str, module_name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "scrape" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_authentication_summary_does_not_expose_credentials(
    monkeypatch: Any,
) -> None:
    module = load_script(
        "02_check_dataforseo_auth.py",
        "check_dataforseo_auth",
    )

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {"status_code": 20000, "tasks": [{"result": [{}]}]}

    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        captured.update({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(module.requests, "get", fake_get)
    summary = module.check_authentication(" login ", " password ")

    assert summary == {
        "http_status": 200,
        "api_status": 20000,
        "authenticated": True,
    }
    assert captured["auth"] == ("login", "password")
    assert "login" not in summary
    assert "password" not in summary


def test_select_submitted_task_ignores_failed_and_keeps_latest() -> None:
    module = load_script(
        "03_check_location_result.py",
        "check_location_result_select",
    )
    task_log = pd.DataFrame(
        [
            {
                "task_tag": "tag-1",
                "task_id": "failed-id",
                "api_type": "maps",
                "submission_status": "failed",
            },
            {
                "task_tag": "tag-1",
                "task_id": "old-id",
                "api_type": "maps",
                "submission_status": "submitted",
            },
            {
                "task_tag": "tag-1",
                "task_id": "new-id",
                "api_type": "maps",
                "submission_status": "submitted",
            },
        ]
    )

    selected = module.select_submitted_task(task_log, "tag-1")

    assert selected["task_id"] == "new-id"
    assert selected["submission_status"] == "submitted"


def test_summarize_ready_task_payload() -> None:
    module = load_script(
        "03_check_location_result.py",
        "check_location_result_summary",
    )
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {"items": [{"title": "A"}, {"title": "B"}]}
                ],
            }
        ],
    }

    summary = module.summarize_task_payload(
        payload,
        api_type="local_finder",
    )

    assert summary == {
        "api_type": "local_finder",
        "response_status": 20000,
        "task_status": 20000,
        "result_ready": True,
        "result_blocks": 1,
        "item_count": 2,
    }
