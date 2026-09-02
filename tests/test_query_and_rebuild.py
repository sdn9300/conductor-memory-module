"""
Tests for MemoryStore query API and rebuild engine (Phase 3).

Validates:
- get_application, list_applications (with status and candidate_id filters), get_history
- get_stale_applications (GHOSTED inference)
- rebuild_derived_state equivalence (ADR-4 / Gate G5)
- rebuild_derived_state also rebuilds domain_cooldowns
"""

import pytest
from datetime import datetime, timezone, timedelta

from src.models import EventType, ApplicationStatus
from src.store import MemoryStore
from src.adapters import (
    from_harvester_event,
    from_align_resume_event,
    from_overture_event,
    from_classified_signal,
)


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test_query_store.db"
    return MemoryStore(db_path=str(db_path))


def test_query_methods(store):
    base_time = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

    # App 1: In progress (APPLIED)
    ev1 = from_harvester_event({
        "job_id": "job_1",
        "application_id": "app_1",
        "candidate_id": "sdn9300",
        "company": "Company A",
        "domain": "companya.com",
        "role": "Engineer",
        "occurred_at": base_time.isoformat(),
    })
    ev2 = from_overture_event({
        "job_id": "job_1",
        "application_id": "app_1",
        "send_id": "send_1",
        "occurred_at": (base_time + timedelta(days=1)).isoformat(),
    })
    store.record_event(ev1)
    store.record_event(ev2)

    # App 2: Offer
    ev3 = from_harvester_event({
        "job_id": "job_2",
        "application_id": "app_2",
        "candidate_id": "candidate_alt",
        "company": "Company B",
        "domain": "companyb.com",
        "role": "Lead",
        "occurred_at": (base_time + timedelta(days=2)).isoformat(),
    })
    ev4 = from_classified_signal({
        "response_id": "resp_2",
        "application_id": "app_2",
        "company": "Company B",
        "role": "Lead",
        "intent_label": "offer_extended",
        "macro_sentiment": "positive",
        "urgency_score": 5,
        "confidence": 0.99,
        "recommended_action": "Accept offer",
        "classified_at": (base_time + timedelta(days=5)).isoformat(),
    })
    store.record_event(ev3)
    store.record_event(ev4)

    # 1. Test get_application
    app1 = store.get_application("app_1")
    assert app1 is not None
    assert app1.company == "Company A"
    assert app1.domain == "companya.com"
    assert app1.candidate_id == "sdn9300"
    assert app1.status == ApplicationStatus.OUTREACHED
    assert len(app1.linked_event_ids) == 2

    assert store.get_application("non_existent") is None

    # 2. Test list_applications with status filter
    all_apps = store.list_applications()
    assert len(all_apps) == 2

    offer_apps = store.list_applications(status=ApplicationStatus.OFFER)
    assert len(offer_apps) == 1
    assert offer_apps[0].application_id == "app_2"

    outreached_apps = store.list_applications(status=ApplicationStatus.OUTREACHED)
    assert len(outreached_apps) == 1
    assert outreached_apps[0].application_id == "app_1"

    # 3. Test list_applications with candidate_id filter
    sdn_apps = store.list_applications(candidate_id="sdn9300")
    assert len(sdn_apps) == 1
    assert sdn_apps[0].application_id == "app_1"

    alt_apps = store.list_applications(candidate_id="candidate_alt")
    assert len(alt_apps) == 1
    assert alt_apps[0].application_id == "app_2"

    # 4. Test get_history
    history1 = store.get_history("app_1")
    assert len(history1) == 2
    assert history1[0].event_type == EventType.JOB_DISCOVERED
    assert history1[1].event_type == EventType.OUTREACH_SENT

    # 5. Test get_stale_applications
    as_of = base_time + timedelta(days=10)
    stale_7_days = store.get_stale_applications(days_silent=7, as_of=as_of)
    assert len(stale_7_days) == 1
    assert stale_7_days[0].application_id == "app_1"

    stale_10_days = store.get_stale_applications(days_silent=10, as_of=as_of)
    assert len(stale_10_days) == 0


def test_rebuild_derived_state_equivalence(store):
    """
    Evaluation Gate G5 / ADR-4 verification:
    Incremental materialization vs rebuild_derived_state() produces identical state,
    including status transitions and domain cooldowns.
    """
    base_time = datetime(2026, 8, 10, 10, 0, 0, tzinfo=timezone.utc)

    # Create multiple events across 3 applications (including one rejection for cooldown)
    events = [
        from_harvester_event({
            "job_id": "job_10", "application_id": "app_10",
            "company": "Alpha", "domain": "alpha.io", "role": "Dev",
            "occurred_at": (base_time).isoformat(),
        }),
        from_align_resume_event({
            "job_id": "job_10", "application_id": "app_10",
            "tailoring_run_id": "tailor_10",
            "occurred_at": (base_time + timedelta(hours=1)).isoformat(),
        }),
        from_overture_event({
            "job_id": "job_10", "application_id": "app_10",
            "send_id": "outreach_10",
            "occurred_at": (base_time + timedelta(hours=2)).isoformat(),
        }),
        from_harvester_event({
            "job_id": "job_20", "application_id": "app_20",
            "company": "Beta", "domain": "beta.io", "role": "ML Engineer",
            "occurred_at": (base_time + timedelta(hours=3)).isoformat(),
        }),
        from_classified_signal({
            "response_id": "resp_10", "application_id": "app_10",
            "company": "Alpha", "domain": "alpha.io", "role": "Dev",
            "intent_label": "interview_invite", "macro_sentiment": "positive",
            "urgency_score": 5, "confidence": 0.95, "recommended_action": "Reply",
            "classified_at": (base_time + timedelta(hours=4)).isoformat(),
        }),
        from_classified_signal({
            "response_id": "resp_20", "application_id": "app_20",
            "company": "Beta", "domain": "beta.io", "role": "ML Engineer",
            "intent_label": "hard_rejection", "macro_sentiment": "negative",
            "urgency_score": 1, "confidence": 0.98,
            "classified_at": (base_time + timedelta(hours=5)).isoformat(),
        }),
    ]

    for ev in events:
        store.record_event(ev)

    # Capture initial incremental state
    initial_records = store.list_applications()
    initial_app10 = store.get_application("app_10")
    initial_app20 = store.get_application("app_20")
    initial_cooldown = store.check_domain_cooldown("beta.io")

    assert initial_cooldown["is_blocked"] is True

    # Perform rebuild
    store.rebuild_derived_state()

    # Capture rebuilt state
    rebuilt_records = store.list_applications()
    rebuilt_app10 = store.get_application("app_10")
    rebuilt_app20 = store.get_application("app_20")
    rebuilt_cooldown = store.check_domain_cooldown("beta.io")

    # Assert exact equivalence
    assert len(initial_records) == len(rebuilt_records)
    assert initial_app10 == rebuilt_app10
    assert initial_app20 == rebuilt_app20
    assert rebuilt_cooldown["is_blocked"] == initial_cooldown["is_blocked"]

    # Check status transitions table rows count
    with store.db.get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) as count FROM status_transitions")
        count = cursor.fetchone()["count"]
        # app_10 had 4 transitions (discovered, tailored, outreached, interview_scheduled)
        # app_20 had 2 transitions (discovered, rejected)
        assert count == 6
