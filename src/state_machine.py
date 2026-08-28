from typing import Optional
from .models import ApplicationStatus, EventType, MemoryEvent

SOFT_TERMINAL_STATUSES = {
    ApplicationStatus.REJECTED,
    ApplicationStatus.OFFER,
    ApplicationStatus.WITHDRAWN,
}

INTERVIEW_INTENTS = {"interview_invite", "scheduling_link"}
OFFER_INTENTS = {"offer_extended"}
REJECTION_INTENTS = {"soft_rejection", "hard_rejection"}

def apply_event(
    current_status: Optional[ApplicationStatus],
    event: MemoryEvent
) -> ApplicationStatus:
    """
    Pure state-machine function computing the new ApplicationStatus 
    given the current status and an incoming MemoryEvent.
    """
    # 1. UNKNOWN event type -> no-op on status (or UNKNOWN if initial event)
    if event.event_type == EventType.UNKNOWN:
        return current_status if current_status is not None else ApplicationStatus.UNKNOWN

    # 2. MANUAL_NOTE with explicit status override
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

        # Ambiguous / info request / under review / etc.
        return ApplicationStatus.RESPONSE_RECEIVED

    return current_status if current_status is not None else ApplicationStatus.UNKNOWN
