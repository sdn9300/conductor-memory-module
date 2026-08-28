from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

class EventType(str, Enum):
    JOB_DISCOVERED = "job_discovered"
    RESUME_TAILORED = "resume_tailored"
    OUTREACH_SENT = "outreach_sent"
    APPLICATION_SUBMITTED = "application_submitted"
    RESPONSE_CLASSIFIED = "response_classified"
    MANUAL_NOTE = "manual_note"
    UNKNOWN = "unknown"

class ApplicationStatus(str, Enum):
    DISCOVERED = "discovered"
    TAILORED = "tailored"
    OUTREACHED = "outreached"
    APPLIED = "applied"
    AWAITING_RESPONSE = "awaiting_response"
    RESPONSE_RECEIVED = "response_received"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"
    WITHDRAWN = "withdrawn"
    UNKNOWN = "unknown"

def _utc_now():
    return datetime.now(timezone.utc)

class MemoryEvent(BaseModel):
    """Append-only. Source of truth. Never mutated after write."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    source_component: str
    application_id: Optional[str] = None
    job_id: Optional[str] = None
    occurred_at: datetime
    ingested_at: datetime = Field(default_factory=_utc_now)
    payload: dict[str, Any]
    raw_source_ref: Optional[str] = None

class StatusTransition(BaseModel):
    application_id: str
    from_status: Optional[ApplicationStatus]
    to_status: ApplicationStatus
    transitioned_at: datetime
    triggering_event_id: str

class ApplicationRecord(BaseModel):
    """Derived / materialized. Rebuildable from memory_events at any time."""
    application_id: str
    job_id: str
    company: str
    role_title: str
    status: ApplicationStatus
    created_at: datetime
    last_updated: datetime
    linked_event_ids: list[str]
