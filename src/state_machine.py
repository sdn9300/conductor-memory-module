"""
Memory Module — State Machine (Pure Function)

Implements MEM-AD-2.0 §4: Transition table for ApplicationStatus.

Pure, deterministic function: same event sequence in → identical derived state out.
This is the core invariant tested by Evaluation Gate G5.

No LLM calls, no side effects, no I/O. (Law 2)
"""

from typing import Optional
from .models import ApplicationStatus, EventType, MemoryEvent


# ---------------------------------------------------------------------------
# Terminal / Classification Intent Sets
# ---------------------------------------------------------------------------

SOFT_TERMINAL_STATUSES = {
    ApplicationStatus.REJECTED,
    ApplicationStatus.OFFER,
    ApplicationStatus.WITHDRAWN,
}

INTERVIEW_INTENTS = {"interview_invite", "scheduling_link"}
OFFER_INTENTS = {"offer_extended"}
REJECTION_INTENTS = {"soft_rejection", "hard_rejection"}
AMBIGUOUS_INTENTS = {"ambiguous", "unclear", "needs_clarification"}


def apply_event(
    current_status: Optional[ApplicationStatus],
    event: MemoryEvent,
) -> ApplicationStatus:
    """
    Pure state-machine function computing the new ApplicationStatus
    given the current status and an incoming MemoryEvent.

    Transition table from MEM-AD-2.0 §4.
    """

    # 1. UNKNOWN event type → no-op on status (or UNKNOWN if initial event)
    if event.event_type == EventType.UNKNOWN:
        return current_status if current_status is not None else ApplicationStatus.UNKNOWN

    # 2. MANUAL_NOTE with explicit status override — escape hatch for human correction
    if event.event_type == EventType.MANUAL_NOTE:
        override = event.payload.get("status_override") or event.payload.get("new_status")
        if override:
            try:
                return ApplicationStatus(override)
            except ValueError:
                pass
        return current_status if current_status is not None else ApplicationStatus.UNKNOWN

    # 3. Soft-terminal states can only be reversed via MANUAL_NOTE override
    if current_status in SOFT_TERMINAL_STATUSES:
        return current_status

    # 4. Event-driven transitions
    if event.event_type == EventType.JOB_DISCOVERED:
        return current_status if current_status is not None else ApplicationStatus.DISCOVERED

    if event.event_type == EventType.RESUME_TAILORED:
        return ApplicationStatus.TAILORED

    if event.event_type == EventType.OUTREACH_SENT:
        return ApplicationStatus.OUTREACHED

    if event.event_type == EventType.APPLICATION_SUBMITTED:
        return ApplicationStatus.APPLIED

    if event.event_type == EventType.RESPONSE_CLASSIFIED:
        intent = event.payload.get("intent_label")
        macro = event.payload.get("macro_sentiment")

        if intent in OFFER_INTENTS:
            return ApplicationStatus.OFFER

        if intent in INTERVIEW_INTENTS:
            return ApplicationStatus.INTERVIEW_SCHEDULED

        if intent in REJECTION_INTENTS or macro == "negative":
            return ApplicationStatus.REJECTED

        if intent in AMBIGUOUS_INTENTS:
            return ApplicationStatus.AMBIGUOUS_OUTCOME

        # Info request / under review / etc. → RESPONSE_RECEIVED
        return ApplicationStatus.RESPONSE_RECEIVED

    # 5. New event types: INTERVIEW_SCHEDULED (from MCP Chief of Staff)
    if event.event_type == EventType.INTERVIEW_SCHEDULED:
        return ApplicationStatus.INTERVIEW_SCHEDULED

    # 6. Informational event types — state passthrough (no transition)
    #    DOSSIER_COMPILED, SKILL_GAP_EVALUATED do not change application status;
    #    they enrich the event trail only.
    if event.event_type in (EventType.DOSSIER_COMPILED, EventType.SKILL_GAP_EVALUATED):
        return current_status if current_status is not None else ApplicationStatus.UNKNOWN

    return current_status if current_status is not None else ApplicationStatus.UNKNOWN
