import hashlib
from datetime import datetime, timezone
from typing import Any, Union, Dict

from .models import MemoryEvent, EventType

def _generate_event_id(source_component: str, raw_ref: str, event_type: str, occurred_at_str: str) -> str:
    """Generates a deterministic event_id for idempotency (ADR-5)."""
    raw_key = f"{source_component}:{raw_ref}:{event_type}:{occurred_at_str}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:32]

def from_harvester_event(data: Dict[str, Any]) -> MemoryEvent:
    """
    Adapter mapping Harvester JOB_DISCOVERED output to a MemoryEvent.
    """
    occurred_at = data.get("occurred_at")
    if isinstance(occurred_at, str):
        occurred_at = datetime.fromisoformat(occurred_at)
    elif not isinstance(occurred_at, datetime):
        occurred_at = datetime.now(timezone.utc)

    raw_ref = str(data.get("raw_source_ref") or data.get("harvest_id") or data.get("job_id") or "ref")
    event_id = data.get("event_id") or _generate_event_id("harvester", raw_ref, EventType.JOB_DISCOVERED.value, occurred_at.isoformat())

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.JOB_DISCOVERED,
        source_component="harvester",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref
    )

def from_align_resume_event(data: Dict[str, Any]) -> MemoryEvent:
    """
    Adapter mapping AlignResume RESUME_TAILORED output to a MemoryEvent.
    """
    occurred_at = data.get("occurred_at")
    if isinstance(occurred_at, str):
        occurred_at = datetime.fromisoformat(occurred_at)
    elif not isinstance(occurred_at, datetime):
        occurred_at = datetime.now(timezone.utc)

    raw_ref = str(data.get("raw_source_ref") or data.get("run_id") or data.get("tailoring_run_id") or "ref")
    event_id = data.get("event_id") or _generate_event_id("align_resume", raw_ref, EventType.RESUME_TAILORED.value, occurred_at.isoformat())

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.RESUME_TAILORED,
        source_component="align_resume",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref
    )

def from_overture_event(data: Dict[str, Any]) -> MemoryEvent:
    """
    Adapter mapping Overture OUTREACH_SENT output to a MemoryEvent.
    """
    occurred_at = data.get("occurred_at")
    if isinstance(occurred_at, str):
        occurred_at = datetime.fromisoformat(occurred_at)
    elif not isinstance(occurred_at, datetime):
        occurred_at = datetime.now(timezone.utc)

    raw_ref = str(data.get("raw_source_ref") or data.get("send_id") or data.get("email_id") or "ref")
    event_id = data.get("event_id") or _generate_event_id("overture", raw_ref, EventType.OUTREACH_SENT.value, occurred_at.isoformat())

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.OUTREACH_SENT,
        source_component="overture",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref
    )

def from_classified_signal(signal: Union[Dict[str, Any], Any]) -> MemoryEvent:
    """
    Adapter mapping Sentiment Classifier v1.0.1 ClassifiedSignal output to a MemoryEvent.
    Reconciled against sentiment_classifier/schemas.py ClassifiedSignal object or dict.
    """
    if hasattr(signal, "model_dump"):
        data = signal.model_dump()
    elif isinstance(signal, dict):
        data = signal.copy()
    else:
        raise ValueError("signal must be a dict or Pydantic model")

    classified_at = data.get("classified_at")
    if isinstance(classified_at, str):
        occurred_at = datetime.fromisoformat(classified_at)
    elif isinstance(classified_at, datetime):
        occurred_at = classified_at
    else:
        occurred_at = datetime.now(timezone.utc)

    raw_ref = str(data.get("response_id") or data.get("raw_source_ref") or "ref")
    event_id = data.get("event_id") or _generate_event_id("sentiment_classifier", raw_ref, EventType.RESPONSE_CLASSIFIED.value, occurred_at.isoformat())

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.RESPONSE_CLASSIFIED,
        source_component="sentiment_classifier",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref
    )
