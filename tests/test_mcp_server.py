"""
Tests for Memory Module FastMCP Server (Phase 6 / CAREEROS Phase 2).

Validates:
- All 7 FastMCP tool endpoints exposed and callable:
  1. record_event
  2. get_application
  3. list_applications
  4. get_history
  5. get_stale_applications
  6. check_domain_cooldown
  7. rebuild_derived_state
- Data fidelity and correct JSON serialization across tools.
"""

import pytest
from datetime import datetime, timezone

from src.store import MemoryStore
from src.mcp_server import (
    create_mcp_server,
    record_event,
    get_application,
    list_applications,
    get_history,
    get_stale_applications,
    check_domain_cooldown,
    rebuild_derived_state,
)


@pytest.fixture
def mcp_test_store(tmp_path):
    db_path = tmp_path / "test_mcp_memory.db"
    store = MemoryStore(db_path=str(db_path))
    create_mcp_server(store=store)
    return store


def test_mcp_record_and_get_application(mcp_test_store):
    # 1. Record job discovery
    res = record_event(
        event_type="job_discovered",
        source_component="gleaner",
        application_id="app_mcp_001",
        job_id="job_mcp_001",
        candidate_id="sdn9300",
        domain="uber.com",
        payload={"company": "Uber", "role_title": "AI Systems Engineer"},
        raw_source_ref="harvester_run_1",
    )
    assert res["status"] == "success"
    assert res["application_id"] == "app_mcp_001"
    assert res["current_status"] == "discovered"

    # 2. Get application
    app_data = get_application("app_mcp_001")
    assert app_data["application_id"] == "app_mcp_001"
    assert app_data["company"] == "Uber"
    assert app_data["domain"] == "uber.com"
    assert app_data["status"] == "discovered"
    assert app_data["candidate_id"] == "sdn9300"

    # 3. Get non-existent application
    missing = get_application("non_existent_app")
    assert "error" in missing


def test_mcp_list_and_history(mcp_test_store):
    # Record events for app A and B
    record_event(
        event_type="job_discovered",
        source_component="gleaner",
        application_id="app_list_a",
        candidate_id="sdn9300",
        domain="google.com",
        payload={"company": "Google", "role_title": "ML Engineer"},
    )
    record_event(
        event_type="outreach_sent",
        source_component="overture",
        application_id="app_list_a",
        payload={"send_id": "send_123"},
    )
    record_event(
        event_type="job_discovered",
        source_component="gleaner",
        application_id="app_list_b",
        candidate_id="other_cand",
        domain="apple.com",
        payload={"company": "Apple", "role_title": "Staff Engineer"},
    )

    # 1. List all
    all_apps = list_applications()
    assert len(all_apps) == 2

    # 2. List filtered by status
    outreached = list_applications(status="outreached")
    assert len(outreached) == 1
    assert outreached[0]["application_id"] == "app_list_a"

    # 3. List filtered by candidate_id
    sdn_apps = list_applications(candidate_id="sdn9300")
    assert len(sdn_apps) == 1
    assert sdn_apps[0]["application_id"] == "app_list_a"

    # 4. Get history
    history_a = get_history("app_list_a")
    assert len(history_a) == 2
    assert history_a[0]["event_type"] == "job_discovered"
    assert history_a[1]["event_type"] == "outreach_sent"


def test_mcp_cooldown_workflow(mcp_test_store):
    # Cooldown before rejection -> is_blocked = False
    cd_pre = check_domain_cooldown("netflix.com")
    assert cd_pre["is_blocked"] is False
    assert cd_pre["cooldown_expires_at"] is None

    # Discover and reject
    record_event(
        event_type="job_discovered",
        source_component="gleaner",
        application_id="app_netflix",
        domain="netflix.com",
        payload={"company": "Netflix", "role_title": "Senior Engineer"},
    )
    record_event(
        event_type="response_classified",
        source_component="sentiment_classifier",
        application_id="app_netflix",
        domain="netflix.com",
        payload={"intent_label": "hard_rejection", "macro_sentiment": "negative"},
    )

    # Cooldown after rejection -> is_blocked = True
    cd_post = check_domain_cooldown("netflix.com")
    assert cd_post["is_blocked"] is True
    assert cd_post["cooldown_expires_at"] is not None


def test_mcp_stale_applications_and_rebuild(mcp_test_store):
    # Record application with immediate activity
    record_event(
        event_type="job_discovered",
        source_component="gleaner",
        application_id="app_stale_test",
        payload={"company": "Databricks", "role_title": "Platform Engineer"},
    )

    # Stale with days_silent=0 -> matches
    stale_apps = get_stale_applications(days_silent=0)
    assert len(stale_apps) >= 1
    assert any(a["application_id"] == "app_stale_test" for a in stale_apps)

    # Rebuild derived state
    rebuild_res = rebuild_derived_state()
    assert rebuild_res["status"] == "success"
    assert rebuild_res["total_applications"] >= 1

    # Verify state after rebuild
    app_rebuilt = get_application("app_stale_test")
    assert app_rebuilt["company"] == "Databricks"
    assert app_rebuilt["status"] == "discovered"
