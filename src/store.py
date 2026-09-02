"""
Memory Module — MemoryStore (Ingestion + Query + Maintenance API)

Implements MEM-AD-2.0 §6: The complete public API surface exposed via FastMCP.

record_event() → ingests, deduplicates, derives state, enforces cooldowns.
All read methods query derived materialized views for performance.
rebuild_derived_state() → drops and replays all derived tables from memory_events.
"""

from datetime import datetime, timezone
from typing import Optional, List
from .models import (
    MemoryEvent,
    ApplicationRecord,
    ApplicationStatus,
    StatusTransition,
    DomainCooldown,
)
from .db import DatabaseHelper
from .state_machine import apply_event


class MemoryStore:
    """
    Main API for the Memory Module.

    Wraps DatabaseHelper with business logic: state machine transitions,
    idempotency enforcement (ADR-5), and 30-day domain cooldown insertion.
    """

    def __init__(self, db_path: str = "memory.db"):
        self.db = DatabaseHelper(db_path=db_path)

    # -------------------------------------------------------------------
    # Write (Ingestion)
    # -------------------------------------------------------------------

    def _derive_and_update_state(self, event: MemoryEvent) -> None:
        """
        Applies state machine transition and updates application_records,
        status_transitions, and domain_cooldowns (on REJECTED).
        """
        if not event.application_id:
            return

        existing_record = self.db.get_application_record(event.application_id)
        from_status = existing_record.status if existing_record else None
        to_status = apply_event(from_status, event)

        if existing_record:
            company = existing_record.company
            domain = event.domain or existing_record.domain
            role_title = existing_record.role_title
            job_id = existing_record.job_id or event.job_id or "unknown_job"
            candidate_id = event.candidate_id or existing_record.candidate_id
            created_at = existing_record.created_at
            linked_ids = existing_record.linked_event_ids + [event.event_id]
        else:
            company = event.payload.get("company", "Unknown Company")
            domain = event.domain or event.payload.get("domain")
            role_title = (
                event.payload.get("role_title")
                or event.payload.get("role", "Unknown Role")
            )
            job_id = event.job_id or event.payload.get("job_id", "unknown_job")
            candidate_id = event.candidate_id or "sdn9300"
            created_at = event.occurred_at
            linked_ids = [event.event_id]

        record = ApplicationRecord(
            application_id=event.application_id,
            job_id=job_id,
            candidate_id=candidate_id,
            company=company,
            domain=domain,
            role_title=role_title,
            status=to_status,
            created_at=created_at,
            last_updated=event.occurred_at,
            linked_event_ids=linked_ids,
        )
        self.db.upsert_application_record(record)

        transition = StatusTransition(
            application_id=event.application_id,
            from_status=from_status,
            to_status=to_status,
            transitioned_at=event.occurred_at,
            triggering_event_id=event.event_id,
        )
        self.db.insert_status_transition(transition)

        # Auto-insert domain cooldown on REJECTED transition
        if (
            to_status == ApplicationStatus.REJECTED
            and from_status != ApplicationStatus.REJECTED
            and domain
        ):
            cooldown = DomainCooldown.from_rejection(
                domain=domain,
                rejected_at=event.occurred_at,
                triggering_event_id=event.event_id,
            )
            self.db.insert_domain_cooldown(cooldown)

    def record_event(self, event: MemoryEvent) -> None:
        """
        Ingests a MemoryEvent.

        Deduplicates by event_id (ADR-5: no-op if event_id already exists).
        Applies state transition and materializes derived application_records,
        status_transitions, and domain_cooldowns.
        """
        existing_event = self.db.get_memory_event(event.event_id)
        if existing_event is not None:
            return

        self.db.insert_memory_event(event)
        self._derive_and_update_state(event)

    # -------------------------------------------------------------------
    # Read (Query)
    # -------------------------------------------------------------------

    def get_application(self, application_id: str) -> Optional[ApplicationRecord]:
        """Fetches the current materialized ApplicationRecord for an application_id."""
        return self.db.get_application_record(application_id)

    def list_applications(
        self,
        status: Optional[ApplicationStatus] = None,
        candidate_id: Optional[str] = None,
    ) -> List[ApplicationRecord]:
        """Lists application records, optionally filtered by status and/or candidate_id."""
        return self.db.list_application_records(status=status, candidate_id=candidate_id)

    def get_history(self, application_id: str) -> List[MemoryEvent]:
        """Returns the full, chronological history of MemoryEvents for an application."""
        return self.db.get_events_for_application(application_id)

    def get_stale_applications(
        self,
        days_silent: int,
        as_of: Optional[datetime] = None,
    ) -> List[ApplicationRecord]:
        """
        Returns in-progress / non-terminal applications that have had no
        activity for at least `days_silent` days, sorted by longest silent first.
        """
        if as_of is None:
            as_of = datetime.now(timezone.utc)
        elif as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)

        all_apps = self.list_applications()
        stale_apps = []
        terminal_statuses = {
            ApplicationStatus.REJECTED,
            ApplicationStatus.OFFER,
            ApplicationStatus.WITHDRAWN,
        }

        for app in all_apps:
            if app.status in terminal_statuses:
                continue

            last_updated = app.last_updated
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)

            delta = as_of - last_updated
            if delta.total_seconds() >= days_silent * 86400:
                stale_apps.append(app)

        stale_apps.sort(key=lambda a: a.last_updated)
        return stale_apps

    def check_domain_cooldown(
        self,
        domain: str,
        as_of: Optional[datetime] = None,
    ) -> dict:
        """
        Check whether a domain is under 30-day rejection cooldown.

        Returns: {"is_blocked": bool, "cooldown_expires_at": datetime | None}
        """
        cooldown = self.db.get_active_cooldown(domain, as_of=as_of)
        if cooldown:
            return {
                "is_blocked": True,
                "cooldown_expires_at": cooldown.cooldown_expires_at,
            }
        return {
            "is_blocked": False,
            "cooldown_expires_at": None,
        }

    # -------------------------------------------------------------------
    # Maintenance
    # -------------------------------------------------------------------

    def rebuild_derived_state(self) -> None:
        """
        Drops and replays application_records, status_transitions, and
        domain_cooldowns from memory_events in occurred_at order.

        Guarantees ADR-4 derived-state equivalence (Gate G5).
        """
        self.db.clear_derived_tables()
        events = self.db.get_all_events()
        for event in events:
            self._derive_and_update_state(event)
