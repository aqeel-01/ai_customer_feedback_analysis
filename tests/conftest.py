"""
conftest.py
===========
Shared pytest fixtures for the test suite.
Only fixtures needed for Step 4 (schemas, ingestion, filtering) are defined here.
DB and LLM fixtures will be added in later steps.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from feedback_analyzer.schemas.input_schema import RawTicket

# ---------------------------------------------------------------------------
# RawTicket fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_raw_ticket() -> RawTicket:
    """Critical bug report ticket with payment crash."""
    return RawTicket(
        ticket_id="T001",
        message="The payment page crashes every time I click 'Checkout' on Chrome. Please fix this ASAP!",
        source="web",
        created_at="2026-10-01T09:00:00Z",
    )


@pytest.fixture
def feature_request_ticket() -> RawTicket:
    """Feature request ticket prefixed with greeting."""
    return RawTicket(
        ticket_id="T002",
        message="Hi team, it would be awesome if you could add a dark mode to the mobile app.",
        source="mobile",
        created_at="2026-10-01T09:05:00Z",
    )


@pytest.fixture
def greeting_ticket() -> RawTicket:
    """Pure conversational pleasantry ticket (should be ignored)."""
    return RawTicket(
        ticket_id="T003",
        message="Hello, hope you are having a nice day!",
        source="email",
        created_at="2026-10-01T09:10:00Z",
    )


@pytest.fixture
def spam_ticket() -> RawTicket:
    """Promotional broadcast. Must be IGNORED."""
    return RawTicket(
        ticket_id="T006",
        message="BUY NOW!!! LIMITED OFFER — 90% OFF ALL PRODUCTS TODAY ONLY!!!",
        source="email",
        created_at="2026-10-01T09:25:00Z",
    )


# ---------------------------------------------------------------------------
# File fixtures (tmp_path-based)
# ---------------------------------------------------------------------------

_SAMPLE_CSV = (
    "ticket_id,message,source,created_at\n"
    "T001,App crashed on checkout.,web,2026-10-01T09:00:00Z\n"
    "T002,Please add dark mode.,mobile,2026-10-01T09:05:00Z\n"
)

_SAMPLE_JSON = [
    {
        "ticket_id": "T001",
        "message": "App crashed on checkout.",
        "source": "web",
        "created_at": "2026-10-01T09:00:00Z",
    },
    {
        "ticket_id": "T002",
        "message": "Please add dark mode.",
        "source": "mobile",
        "created_at": "2026-10-01T09:05:00Z",
    },
]


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    """A valid two-row CSV input file."""
    f = tmp_path / "input.csv"
    f.write_text(_SAMPLE_CSV, encoding="utf-8")
    return f


@pytest.fixture
def json_file(tmp_path: Path) -> Path:
    """A valid two-record JSON input file."""
    f = tmp_path / "input.json"
    f.write_text(json.dumps(_SAMPLE_JSON, indent=2), encoding="utf-8")
    return f
