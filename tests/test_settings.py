"""Tests for central project configuration."""

from pathlib import Path

import yaml


def test_google_reviews_configuration() -> None:
    config = yaml.safe_load(
        Path("config/settings.yaml").read_text(encoding="utf-8")
    )
    dataforseo = config["dataforseo"]
    endpoints = dataforseo["endpoints"]

    assert endpoints["reviews_post"].endswith("/reviews/task_post")
    assert endpoints["reviews_get"].endswith(
        "/reviews/task_get/{task_id}"
    )
    assert endpoints["reviews_tasks_ready"].endswith(
        "/reviews/tasks_ready"
    )

    assert 1 <= dataforseo["review_task_batch_size"] <= 100
    assert dataforseo["review_sort_by"] in {
        "newest",
        "highest_rating",
        "lowest_rating",
        "relevant",
    }
    assert dataforseo["review_depth_minimum"] >= 1
    assert dataforseo["review_depth_maximum"] <= 4490
    assert (
        dataforseo["review_depth_minimum"]
        <= dataforseo["review_depth_maximum"]
    )
    assert dataforseo["review_depth_multiple"] == 10
