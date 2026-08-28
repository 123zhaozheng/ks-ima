from __future__ import annotations

import asyncio
import os
import sys

import pytest


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Make the container integration gate fail instead of silently skipping Postgres tests."""
    if os.environ.get("IMA_REQUIRE_POSTGRES") != "1":
        return
    if not os.environ.get("IMA_TEST_DATABASE_URL"):
        pytest.exit("IMA_REQUIRE_POSTGRES=1 requires IMA_TEST_DATABASE_URL", returncode=2)
    postgres_items = [item for item in items if item.get_closest_marker("postgres")]
    if len(postgres_items) != 40:
        pytest.exit(
            "expected exactly 40 Postgres tests in the integration gate, "
            f"found {len(postgres_items)}",
            returncode=2,
        )
