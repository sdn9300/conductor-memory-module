import pytest
from datetime import datetime, timezone

from src.models import EventType, ApplicationStatus
from src.store import MemoryStore
from src.adapters import (
    from_harvester_event,
    from_align_resume_event,
    from_overture_event,
    from_classified_signal
)

@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test_store.db"
    return MemoryStore(db_path=str(db_path))

def test_record_event_idempotency(store):
    event = from_harvester_event({
        "job_id": "job_001",
        "application_id": "app_001",
        "company": "Acme Corp",
        "role_title": "Software Engineer",
        "harvest_id": "harvest_999",
        "occurred_at": datetime.now(timezone.utc).isoformat()
    })

    # First record
    store.record_event(event)
    rec1 = store.db.get_application_record("app_001")
    assert rec1 is not None
    assert rec1.status == ApplicationStatus.DISCOVERED
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
        "role": "Backend Developer",
        "occurred_at": now.isoformat()
    })
    store.record_event(ev1)
    assert store.db.get_application_record(app_id).status == ApplicationStatus.DISCOVERED

    # 2. Resume Tailored
    ev2 = from_align_resume_event({
        "job_id": "job_100",
        "application_id": app_id,
        "tailoring_run_id": "run_001",
        "occurred_at": now.isoformat()
    })
    store.record_event(ev2)
    assert store.db.get_application_record(app_id).status == ApplicationStatus.TAILORED

    # 3. Outreach Sent
    ev3 = from_overture_event({
        "job_id": "job_100",
        "application_id": app_id,
        "send_id": "email_777",
        "occurred_at": now.isoformat()
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
        "classified_at": now.isoformat()
    })
    store.record_event(ev4)
    assert store.db.get_application_record(app_id).status == ApplicationStatus.INTERVIEW_SCHEDULED
