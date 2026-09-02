"""
Memory Module — Core Data Models (Pydantic v2)

Implements MEM-AD-2.0 §3: EventType, ApplicationStatus, MemoryEvent,
StatusTransition, ApplicationRecord, DomainCooldown.

Governance: Law 8 (Memory Event Sourcing & Immutability)
"""

from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
import hashlib
import uuid


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """All event types produced by CareerOS subsystems."""
    JOB_DISCOVERED        = "job_discovered"
    RESUME_TAILORED       = "resume_tailored"
    OUTREACH_SENT         = "outreach_sent"
    APPLICATION_SUBMITTED = "application_submitted"
    RESPONSE_CLASSIFIED   = "response_classified"
    INTERVIEW_SCHEDULED   = "interview_scheduled"
    DOSSIER_COMPILED      = "dossier_compiled"
    SKILL_GAP_EVALUATED   = "skill_gap_evaluated"
    MANUAL_NOTE           = "manual_note"
    UNKNOWN               = "unknown"  # Fallback — never reject an event (Law 6)


class ApplicationStatus(str, Enum):
    """Lifecycle states for a single job application."""
    DISCOVERED         = "discovered"
    TAILORED           = "tailored"
    OUTREACHED         = "outreached"
    APPLIED            = "applied"
    AWAITING_RESPONSE  = "awaiting_response"
    RESPONSE_RECEIVED  = "response_received"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    OFFER              = "offer"
    REJECTED           = "rejected"
    GHOSTED            = "ghosted"           # Computed at query time — not event-driven
    WITHDRAWN          = "withdrawn"
    AMBIGUOUS_OUTCOME  = "ambiguous_outcome"  # Held for manual review (MEM-AD-2.0 §4)
    UNKNOWN            = "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def generate_event_id(
    source_component: str,
    raw_source_ref: str,
    event_type: str,
    occurred_at_iso: str,
) -> str:
    """
    Deterministic event_id for idempotency (ADR-5).

    hash = sha256(source_component : raw_source_ref : event_type : occurred_at)
    Truncated to 32 hex chars for readability.
    """
    raw_key = f"{source_component}:{raw_source_ref}:{event_type}:{occurred_at_iso}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Core Models
# ---------------------------------------------------------------------------

class MemoryEvent(BaseModel):
    """
    Append-only. Source of truth. Never mutated after write.

    Every event produced by any CareerOS subsystem is recorded as a MemoryEvent.
    The payload dict is schema-on-read; validated per-type at the adapter boundary.
    """
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Deterministic hash for idempotency: hash(source+ref+type+occurred_at)"
    )
    event_type: EventType
    source_component: str                     # e.g. "sentiment_classifier", "pdf_auto_apply"
    application_id: Optional[str] = None
    job_id: Optional[str] = None
    candidate_id: Optional[str] = None        # Opaque FK to Candidate Profile JSON [10]
    domain: Optional[str] = None              # ATS/company domain for cooldown tracking
    occurred_at: datetime                     # Producer-reported wall-clock time
    ingested_at: datetime = Field(default_factory=_utc_now)
    payload: dict[str, Any]                   # Schema-on-read; validated per-type at boundary
    raw_source_ref: Optional[str] = None      # e.g. originating ClassifiedSignal ID


class StatusTransition(BaseModel):
    """Audit trail entry recording a single status change."""
    application_id: str
    from_status: Optional[ApplicationStatus]  # None for the creating (first) event
    to_status: ApplicationStatus
    transitioned_at: datetime
    triggering_event_id: str


class ApplicationRecord(BaseModel):
    """
    Derived / materialized view. Rebuildable from memory_events at any time.

    Represents the current lifecycle state of a single job application.
    """
    application_id: str
    job_id: str
    candidate_id: str = "sdn9300"             # Default candidate until multi-user
    company: str
    domain: Optional[str] = None              # Normalized company domain
    role_title: str
    status: ApplicationStatus
    created_at: datetime
    last_updated: datetime
    linked_event_ids: list[str]


class DomainCooldown(BaseModel):
    """
    30-day rejection cooldown per company domain.

    Automatically inserted when a status transition to REJECTED is materialized.
    `is_active` is computed at query time based on current datetime vs cooldown_expires_at.
    """
    domain: str
    rejected_at: datetime
    cooldown_expires_at: datetime              # = rejected_at + timedelta(days=30)
    triggering_event_id: str
    is_active: bool = True                    # Computed at query time

    @classmethod
    def from_rejection(
        cls,
        domain: str,
        rejected_at: datetime,
        triggering_event_id: str,
        cooldown_days: int = 30,
    ) -> "DomainCooldown":
        """Factory method to create a cooldown from a rejection event."""
        return cls(
            domain=domain,
            rejected_at=rejected_at,
            cooldown_expires_at=rejected_at + timedelta(days=cooldown_days),
            triggering_event_id=triggering_event_id,
            is_active=True,
        )
