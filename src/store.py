from datetime import datetime, timezone
from typing import Optional, List
from .models import MemoryEvent, ApplicationRecord, ApplicationStatus, StatusTransition
from .db import DatabaseHelper
from .state_machine import apply_event

class MemoryStore:
    def __init__(self, db_path: str = "memory.db"):
        self.db = DatabaseHelper(db_path=db_path)

    def _derive_and_update_state(self, event: MemoryEvent) -> None:
        """
        Applies state machine transition and updates application_records & status_transitions.
        """
        if not event.application_id:
            return

        existing_record = self.db.get_application_record(event.application_id)
        from_status = existing_record.status if existing_record else None
        to_status = apply_event(from_status, event)

        if existing_record:
            company = existing_record.company
            role_title = existing_record.role_title
            job_id = existing_record.job_id or event.job_id or "unknown_job"
            created_at = existing_record.created_at
            linked_ids = existing_record.linked_event_ids + [event.event_id]
        else:
            company = event.payload.get("company", "Unknown Company")
            role_title = event.payload.get("role_title") or event.payload.get("role", "Unknown Role")
            job_id = event.job_id or event.payload.get("job_id", "unknown_job")
            created_at = event.occurred_at
            linked_ids = [event.event_id]

        record = ApplicationRecord(
            application_id=event.application_id,
            job_id=job_id,
            company=company,
            role_title=role_title,
            status=to_status,
            created_at=created_at,
            last_updated=event.occurred_at,
            linked_event_ids=linked_ids
        )
        self.db.upsert_application_record(record)

        transition = StatusTransition(
            application_id=event.application_id,
            from_status=from_status,
            to_status=to_status,
            transitioned_at=event.occurred_at,
            triggering_event_id=event.event_id
        )
        self.db.insert_status_transition(transition)

    def record_event(self, event: MemoryEvent) -> None:
        """
        Ingests a MemoryEvent.
        Deduplicates by event_id (ADR-5: no-op if event_id already exists).
        Applies state transition and materializes derived application_records & status_transitions.
        """
        existing_event = self.db.get_memory_event(event.event_id)
        if existing_event is not None:
            return

        self.db.insert_memory_event(event)
        self._derive_and_update_state(event)

    def get_application(self, application_id: str) -> Optional[ApplicationRecord]:
        """
        Fetches the current materialized ApplicationRecord for an application_id.
        """
        return self.db.get_application_record(application_id)

    def list_applications(
        self, status: Optional[ApplicationStatus] = None
    ) -> List[ApplicationRecord]:
        """
        Lists application records, optionally filtered by status.
        """
        return self.db.list_application_records(status=status)

    def get_history(self, application_id: str) -> List[MemoryEvent]:
        """
        Returns the full, chronological history of MemoryEvents for an application.
        """
        return self.db.get_events_for_application(application_id)

    def get_stale_applications(
        self, days_silent: int, as_of: Optional[datetime] = None
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

    def rebuild_derived_state(self) -> None:
        """
        Drops and replays application_records / status_transitions
        from memory_events in occurred_at order.
        Guarantees ADR-4 derived-state equivalence (Gate G5).
        """
        self.db.clear_derived_tables()
        events = self.db.get_all_events()
        for event in events:
            self._derive_and_update_state(event)
