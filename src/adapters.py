"""
Memory Module — Producer Adapters

Maps raw output from each CareerOS subsystem into a canonical MemoryEvent.

Each adapter:
1. Parses occurred_at from the producer's native format
2. Generates a deterministic event_id via ADR-5 hash
3. Extracts candidate_id and domain when available
4. Returns a fully-formed MemoryEvent ready for record_event()

Integration Contracts: MEM-AD-2.0 §7
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Union, Dict

from .models import MemoryEvent, EventType


# ---------------------------------------------------------------------------
# Shared Helpers
# ---------------------------------------------------------------------------

def _generate_event_id(
    source_component: str,
    raw_ref: str,
    event_type: str,
    occurred_at_str: str,
) -> str:
    """Generates a deterministic event_id for idempotency (ADR-5)."""
    raw_key = f"{source_component}:{raw_ref}:{event_type}:{occurred_at_str}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:32]


def _parse_occurred_at(data: Dict[str, Any], key: str = "occurred_at") -> datetime:
    """Parse a datetime from data dict, falling back to UTC now."""
    value = data.get(key)
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    elif isinstance(value, datetime):
        return value
    return datetime.now(timezone.utc)


def _extract_domain(data: Dict[str, Any]) -> str | None:
    """Extract normalized domain from data dict."""
    return data.get("domain") or data.get("ats_domain") or None


def _extract_candidate_id(data: Dict[str, Any]) -> str | None:
    """Extract candidate_id from data dict if present, else None."""
    return data.get("candidate_id") or None


# ---------------------------------------------------------------------------
# Adapter: The Gleaner [1] → JOB_DISCOVERED
# ---------------------------------------------------------------------------

def from_harvester_event(data: Dict[str, Any]) -> MemoryEvent:
    """
    Adapter mapping Gleaner JOB_DISCOVERED output to a MemoryEvent.

    Expected payload fields: job_id, application_id, company, role_title/role,
    domain, harvest_id/raw_source_ref, occurred_at
    """
    occurred_at = _parse_occurred_at(data)
    raw_ref = str(
        data.get("raw_source_ref")
        or data.get("harvest_id")
        or data.get("job_id")
        or "ref"
    )
    event_id = data.get("event_id") or _generate_event_id(
        "gleaner", raw_ref, EventType.JOB_DISCOVERED.value, occurred_at.isoformat()
    )

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.JOB_DISCOVERED,
        source_component="gleaner",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        candidate_id=_extract_candidate_id(data),
        domain=_extract_domain(data),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref,
    )


# ---------------------------------------------------------------------------
# Adapter: AlignResume [2] → RESUME_TAILORED
# ---------------------------------------------------------------------------

def from_align_resume_event(data: Dict[str, Any]) -> MemoryEvent:
    """
    Adapter mapping AlignResume RESUME_TAILORED output to a MemoryEvent.

    Expected payload fields: application_id, job_id, tailoring_run_id,
    resume_diff_summary, occurred_at
    """
    occurred_at = _parse_occurred_at(data)
    raw_ref = str(
        data.get("raw_source_ref")
        or data.get("run_id")
        or data.get("tailoring_run_id")
        or "ref"
    )
    event_id = data.get("event_id") or _generate_event_id(
        "align_resume", raw_ref, EventType.RESUME_TAILORED.value, occurred_at.isoformat()
    )

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.RESUME_TAILORED,
        source_component="align_resume",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        candidate_id=_extract_candidate_id(data),
        domain=_extract_domain(data),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref,
    )


# ---------------------------------------------------------------------------
# Adapter: Overture Outreach [3] → OUTREACH_SENT
# ---------------------------------------------------------------------------

def from_overture_event(data: Dict[str, Any]) -> MemoryEvent:
    """
    Adapter mapping Overture OUTREACH_SENT output to a MemoryEvent.

    Expected payload fields: application_id, job_id, send_id/email_id, occurred_at
    """
    occurred_at = _parse_occurred_at(data)
    raw_ref = str(
        data.get("raw_source_ref")
        or data.get("send_id")
        or data.get("email_id")
        or "ref"
    )
    event_id = data.get("event_id") or _generate_event_id(
        "overture", raw_ref, EventType.OUTREACH_SENT.value, occurred_at.isoformat()
    )

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.OUTREACH_SENT,
        source_component="overture",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        candidate_id=_extract_candidate_id(data),
        domain=_extract_domain(data),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref,
    )


# ---------------------------------------------------------------------------
# Adapter: Sentiment Classifier [9] → RESPONSE_CLASSIFIED
# ---------------------------------------------------------------------------

def from_classified_signal(signal: Union[Dict[str, Any], Any]) -> MemoryEvent:
    """
    Adapter mapping Sentiment Classifier v1.0.1 ClassifiedSignal output to a MemoryEvent.

    Reconciled against sentiment_classifier/schemas.py ClassifiedSignal object or dict.
    Handles both Pydantic model instances and raw dicts.
    """
    if hasattr(signal, "model_dump"):
        data = signal.model_dump()
    elif isinstance(signal, dict):
        data = signal.copy()
    else:
        raise ValueError("signal must be a dict or Pydantic model")

    occurred_at = _parse_occurred_at(data, key="classified_at")
    raw_ref = str(
        data.get("response_id")
        or data.get("raw_source_ref")
        or "ref"
    )
    event_id = data.get("event_id") or _generate_event_id(
        "sentiment_classifier",
        raw_ref,
        EventType.RESPONSE_CLASSIFIED.value,
        occurred_at.isoformat(),
    )

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.RESPONSE_CLASSIFIED,
        source_component="sentiment_classifier",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        candidate_id=_extract_candidate_id(data),
        domain=_extract_domain(data),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref,
    )


# ---------------------------------------------------------------------------
# Adapter: PDF Auto-Apply [7] → APPLICATION_SUBMITTED
# ---------------------------------------------------------------------------

def from_auto_apply_receipt(data: Dict[str, Any]) -> MemoryEvent:
    """
    Adapter mapping PDF Auto-Apply submission receipt to a MemoryEvent.

    Expected payload fields: application_id, job_id, submission_id/attempt_id,
    ats_domain, pdf_artifact_path, form_fields_filled, occurred_at/completed_at
    """
    occurred_at = _parse_occurred_at(data, key="completed_at")
    if occurred_at == datetime.now(timezone.utc):
        # Fallback: try occurred_at, started_at
        occurred_at = _parse_occurred_at(data, key="occurred_at")
        if occurred_at == datetime.now(timezone.utc):
            occurred_at = _parse_occurred_at(data, key="started_at")

    raw_ref = str(
        data.get("raw_source_ref")
        or data.get("submission_id")
        or data.get("attempt_id")
        or "ref"
    )
    event_id = data.get("event_id") or _generate_event_id(
        "pdf_auto_apply",
        raw_ref,
        EventType.APPLICATION_SUBMITTED.value,
        occurred_at.isoformat(),
    )

    # Extract domain from nested job object or top-level
    domain = _extract_domain(data)
    if not domain and isinstance(data.get("job"), dict):
        domain = data["job"].get("domain") or data["job"].get("ats_domain")

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.APPLICATION_SUBMITTED,
        source_component="pdf_auto_apply",
        application_id=data.get("application_id"),
        job_id=data.get("job_id") or (data.get("job", {}).get("job_id") if isinstance(data.get("job"), dict) else None),
        candidate_id=_extract_candidate_id(data),
        domain=domain,
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref,
    )


# ---------------------------------------------------------------------------
# Adapter: MCP Chief of Staff [6] → INTERVIEW_SCHEDULED
# ---------------------------------------------------------------------------

def from_chief_of_staff_event(data: Dict[str, Any]) -> MemoryEvent:
    """
    Adapter mapping MCP Chief of Staff interview scheduling event to a MemoryEvent.

    Expected payload fields: application_id, job_id, calendar_event_id,
    interviewer, scheduled_at, platform, occurred_at
    """
    occurred_at = _parse_occurred_at(data)
    raw_ref = str(
        data.get("raw_source_ref")
        or data.get("calendar_event_id")
        or "ref"
    )
    event_id = data.get("event_id") or _generate_event_id(
        "chief_of_staff",
        raw_ref,
        EventType.INTERVIEW_SCHEDULED.value,
        occurred_at.isoformat(),
    )

    return MemoryEvent(
        event_id=event_id,
        event_type=EventType.INTERVIEW_SCHEDULED,
        source_component="chief_of_staff",
        application_id=data.get("application_id"),
        job_id=data.get("job_id"),
        candidate_id=_extract_candidate_id(data),
        domain=_extract_domain(data),
        occurred_at=occurred_at,
        payload=data,
        raw_source_ref=raw_ref,
    )
