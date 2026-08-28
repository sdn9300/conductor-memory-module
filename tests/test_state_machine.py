import pytest
from datetime import datetime, timezone

from src.models import ApplicationStatus, EventType, MemoryEvent
from src.state_machine import apply_event

def make_event(event_type: EventType, payload: dict = None) -> MemoryEvent:
    return MemoryEvent(
        event_type=event_type,
        source_component="test",
        occurred_at=datetime.now(timezone.utc),
        payload=payload or {}
    )

def test_job_discovered_transitions():
    event = make_event(EventType.JOB_DISCOVERED)
    assert apply_event(None, event) == ApplicationStatus.DISCOVERED
    assert apply_event(ApplicationStatus.DISCOVERED, event) == ApplicationStatus.DISCOVERED

def test_resume_tailored_transitions():
    event = make_event(EventType.RESUME_TAILORED)
    assert apply_event(ApplicationStatus.DISCOVERED, event) == ApplicationStatus.TAILORED
    assert apply_event(None, event) == ApplicationStatus.TAILORED

def test_outreach_sent_transitions():
    event = make_event(EventType.OUTREACH_SENT)
    assert apply_event(ApplicationStatus.TAILORED, event) == ApplicationStatus.OUTREACHED
    assert apply_event(ApplicationStatus.DISCOVERED, event) == ApplicationStatus.OUTREACHED

def test_application_submitted_transitions():
    event = make_event(EventType.APPLICATION_SUBMITTED)
    assert apply_event(ApplicationStatus.TAILORED, event) == ApplicationStatus.APPLIED
    assert apply_event(ApplicationStatus.OUTREACHED, event) == ApplicationStatus.APPLIED

def test_response_classified_interview():
    event = make_event(EventType.RESPONSE_CLASSIFIED, {"intent_label": "interview_invite", "macro_sentiment": "positive"})
    assert apply_event(ApplicationStatus.APPLIED, event) == ApplicationStatus.INTERVIEW_SCHEDULED
    assert apply_event(ApplicationStatus.OUTREACHED, event) == ApplicationStatus.INTERVIEW_SCHEDULED

def test_response_classified_rejection():
    event = make_event(EventType.RESPONSE_CLASSIFIED, {"intent_label": "hard_rejection", "macro_sentiment": "negative"})
    assert apply_event(ApplicationStatus.APPLIED, event) == ApplicationStatus.REJECTED
    assert apply_event(ApplicationStatus.INTERVIEW_SCHEDULED, event) == ApplicationStatus.REJECTED

def test_response_classified_ambiguous():
    event = make_event(EventType.RESPONSE_CLASSIFIED, {"intent_label": "request_for_info", "macro_sentiment": "neutral"})
    assert apply_event(ApplicationStatus.APPLIED, event) == ApplicationStatus.RESPONSE_RECEIVED
    assert apply_event(ApplicationStatus.OUTREACHED, event) == ApplicationStatus.RESPONSE_RECEIVED

def test_response_classified_offer():
    event = make_event(EventType.RESPONSE_CLASSIFIED, {"intent_label": "offer_extended", "macro_sentiment": "positive"})
    assert apply_event(ApplicationStatus.INTERVIEW_SCHEDULED, event) == ApplicationStatus.OFFER

def test_manual_note_override():
    event = make_event(EventType.MANUAL_NOTE, {"status_override": "interview_scheduled"})
    assert apply_event(ApplicationStatus.REJECTED, event) == ApplicationStatus.INTERVIEW_SCHEDULED

def test_soft_terminal_protection():
    # Once in soft terminal (REJECTED, OFFER, WITHDRAWN), automatic events cannot change status
    event = make_event(EventType.RESPONSE_CLASSIFIED, {"intent_label": "interview_invite"})
    assert apply_event(ApplicationStatus.REJECTED, event) == ApplicationStatus.REJECTED
    assert apply_event(ApplicationStatus.OFFER, event) == ApplicationStatus.OFFER

def test_unknown_event_type():
    event = make_event(EventType.UNKNOWN)
    assert apply_event(ApplicationStatus.APPLIED, event) == ApplicationStatus.APPLIED
    assert apply_event(None, event) == ApplicationStatus.UNKNOWN
