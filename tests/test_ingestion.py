"""
Tests for MemoryStore ingestion API, deduplication, and producer adapters (Phase 2).

Validates:
- Event ingestion idempotency (ADR-5)
- Full application lifecycle event ingestion
- All producer adapters (Gleaner, AlignResume, Overture, Sentiment, PDF Auto-Apply, Chief of Staff)
- Auto-creation of DomainCooldown on REJECTED status transition
"""

import pytest
from datetime import datetime, timezone

from src.models import EventType, ApplicationStatus
from src.store import MemoryStore
from src.adapters import (
    from_harvester_event,
    from_align_resume_event,
    from_overture_event,
    from_classified_signal,
    from_auto_apply_receipt,
    from_chief_of_staff_event,
)


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test_store.db"
    return MemoryStore(db_path=str(db_path))


def test_record_event_idempotency(store):
    event = from_harvester_event({
        "job_id": "job_001",
        "application_id": "app_001",
        "candidate_id": "sdn9300",
        "company": "Acme Corp",
        "domain": "acme.com",
        "role_title": "Software Engineer",
        "harvest_id": "harvest_999",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    })

    # First record
    store.record_event(event)
    rec1 = store.db.get_application_record("app_001")
    assert rec1 is not None
    assert rec1.status == ApplicationStatus.DISCOVERED
    assert rec1.candidate_id == "sdn9300"
    assert rec1.domain == "acme.com"
    assert len(rec1.linked_event_ids) == 1

    # Second record with identical event (same event_id)
    store.record_event(event)
    rec2 = store.db.get_application_record("app_001")
    assert rec2 is not None
    # Confirm no duplicate linked event or double state transition occurred
    assert len(rec2.linked_event_ids) == 1


def test_full_lifecycle_ingestion(store):
    app_id = "app_lifecycle_001"
    now = datetime.now(timezone.utc)

    # 1. Job Discovered
    ev1 = from_harvester_event({
        "job_id": "job_100",
        "application_id": app_id,
        "company": "TechCorp",
        "domain": "techcorp.io",
        "role": "Backend Developer",
        "occurred_at": now.isoformat(),
    })
    store.record_event(ev1)
    assert store.db.get_application_record(app_id).status == ApplicationStatus.DISCOVERED

    # 2. Resume Tailored
    ev2 = from_align_resume_event({
        "job_id": "job_100",
        "application_id": app_id,
        "tailoring_run_id": "run_001",
        "occurred_at": now.isoformat(),
    })
    store.record_event(ev2)
    assert store.db.get_application_record(app_id).status == ApplicationStatus.TAILORED

    # 3. Outreach Sent
    ev3 = from_overture_event({
        "job_id": "job_100",
        "application_id": app_id,
        "send_id": "email_777",
        "occurred_at": now.isoformat(),
    })
    store.record_event(ev3)
    assert store.db.get_application_record(app_id).status == ApplicationStatus.OUTREACHED

    # 4. Response Classified (Interview Invite)
    ev4 = from_classified_signal({
        "response_id": "resp_888",
        "application_id": app_id,
        "company": "TechCorp",
        "role": "Backend Developer",
        "macro_sentiment": "positive",
        "intent_label": "interview_invite",
        "urgency_score": 5,
        "confidence": 0.98,
        "recommended_action": "Schedule call",
        "classified_at": now.isoformat(),
    })
    store.record_event(ev4)
    assert store.db.get_application_record(app_id).status == ApplicationStatus.INTERVIEW_SCHEDULED


def test_auto_apply_receipt_adapter(store):
    app_id = "app_auto_apply_001"
    now = datetime.now(timezone.utc)

    # First discover
    ev1 = from_harvester_event({
        "job_id": "job_200",
        "application_id": app_id,
        "company": "OpenAI",
        "domain": "openai.com",
        "role_title": "ML Engineer",
        "occurred_at": now.isoformat(),
    })
    store.record_event(ev1)

    # Auto-apply submitted
    ev2 = from_auto_apply_receipt({
        "application_id": app_id,
        "job_id": "job_200",
        "submission_id": "sub_999",
        "ats_domain": "greenhouse.io",
        "completed_at": now.isoformat(),
        "pdf_artifact_path": "/path/to/tailored_resume.pdf",
    })
    store.record_event(ev2)

    rec = store.db.get_application_record(app_id)
    assert rec.status == ApplicationStatus.APPLIED
    assert len(rec.linked_event_ids) == 2


def test_chief_of_staff_adapter(store):
    app_id = "app_cos_001"
    now = datetime.now(timezone.utc)

    # First discover & apply
    ev1 = from_harvester_event({
        "job_id": "job_300",
        "application_id": app_id,
        "company": "Google",
        "role_title": "Staff Engineer",
        "occurred_at": now.isoformat(),
    })
    store.record_event(ev1)

    # Chief of Staff schedules interview
    ev2 = from_chief_of_staff_event({
        "application_id": app_id,
        "job_id": "job_300",
        "calendar_event_id": "cal_evt_123",
        "interviewer": "Sundar Pichai",
        "scheduled_at": "2026-09-01T15:00:00Z",
        "occurred_at": now.isoformat(),
    })
    store.record_event(ev2)

    rec = store.db.get_application_record(app_id)
    assert rec.status == ApplicationStatus.INTERVIEW_SCHEDULED


def test_rejection_auto_creates_domain_cooldown(store):
    app_id = "app_reject_cd"
    now = datetime.now(timezone.utc)

    # Discover with domain
    ev1 = from_harvester_event({
        "job_id": "job_reject",
        "application_id": app_id,
        "company": "Amazon",
        "domain": "amazon.com",
        "role_title": "SDE-2",
        "occurred_at": now.isoformat(),
    })
    store.record_event(ev1)

    # Check cooldown before rejection → not blocked
    cd_before = store.check_domain_cooldown("amazon.com")
    assert cd_before["is_blocked"] is False

    # Receive rejection
    ev2 = from_classified_signal({
        "response_id": "resp_reject_001",
        "application_id": app_id,
        "company": "Amazon",
        "domain": "amazon.com",
        "macro_sentiment": "negative",
        "intent_label": "hard_rejection",
        "urgency_score": 1,
        "confidence": 0.99,
        "classified_at": now.isoformat(),
    })
    store.record_event(ev2)

    # Status must be REJECTED
    rec = store.db.get_application_record(app_id)
    assert rec.status == ApplicationStatus.REJECTED

    # Cooldown must now be active!
    cd_after = store.check_domain_cooldown("amazon.com")
    assert cd_after["is_blocked"] is True
    assert cd_after["cooldown_expires_at"] is not None
