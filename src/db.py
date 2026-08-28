import sqlite3
import json
from contextlib import contextmanager
from typing import Generator, Optional, List
from datetime import datetime

from .models import MemoryEvent, EventType, ApplicationRecord, ApplicationStatus, StatusTransition

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_events (
    event_id          TEXT PRIMARY KEY,
    event_type        TEXT NOT NULL,
    source_component  TEXT NOT NULL,
    application_id    TEXT,
    job_id            TEXT,
    occurred_at       TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    payload_json      TEXT NOT NULL,
    raw_source_ref    TEXT
);

CREATE TABLE IF NOT EXISTS application_records (
    application_id  TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL,
    company         TEXT NOT NULL,
    role_title      TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_updated    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS status_transitions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id      TEXT NOT NULL,
    from_status         TEXT,
    to_status           TEXT NOT NULL,
    transitioned_at     TEXT NOT NULL,
    triggering_event_id TEXT NOT NULL,
    FOREIGN KEY (application_id) REFERENCES application_records(application_id),
    FOREIGN KEY (triggering_event_id) REFERENCES memory_events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_events_application ON memory_events(application_id);
CREATE INDEX IF NOT EXISTS idx_events_type        ON memory_events(event_type);
CREATE INDEX IF NOT EXISTS idx_transitions_app    ON status_transitions(application_id);
"""

class DatabaseHelper:
    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self._initialize_schema()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _initialize_schema(self):
        with self.get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def insert_memory_event(self, event: MemoryEvent) -> None:
        query = """
            INSERT INTO memory_events (
                event_id, event_type, source_component, application_id,
                job_id, occurred_at, ingested_at, payload_json, raw_source_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            conn.execute(query, (
                event.event_id,
                event.event_type.value,
                event.source_component,
                event.application_id,
                event.job_id,
                event.occurred_at.isoformat(),
                event.ingested_at.isoformat(),
                json.dumps(event.payload),
                event.raw_source_ref
            ))
            conn.commit()

    def get_memory_event(self, event_id: str) -> Optional[MemoryEvent]:
        query = "SELECT * FROM memory_events WHERE event_id = ?"
        with self.get_connection() as conn:
            cursor = conn.execute(query, (event_id,))
            row = cursor.fetchone()

        if not row:
            return None

        return MemoryEvent(
            event_id=row["event_id"],
            event_type=EventType(row["event_type"]),
            source_component=row["source_component"],
            application_id=row["application_id"],
            job_id=row["job_id"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            ingested_at=datetime.fromisoformat(row["ingested_at"]),
            payload=json.loads(row["payload_json"]),
            raw_source_ref=row["raw_source_ref"]
        )

    def get_events_for_application(self, application_id: str) -> List[MemoryEvent]:
        query = "SELECT * FROM memory_events WHERE application_id = ? ORDER BY occurred_at ASC, ingested_at ASC"
        with self.get_connection() as conn:
            cursor = conn.execute(query, (application_id,))
            rows = cursor.fetchall()

        events = []
        for row in rows:
            events.append(MemoryEvent(
                event_id=row["event_id"],
                event_type=EventType(row["event_type"]),
                source_component=row["source_component"],
                application_id=row["application_id"],
                job_id=row["job_id"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                ingested_at=datetime.fromisoformat(row["ingested_at"]),
                payload=json.loads(row["payload_json"]),
                raw_source_ref=row["raw_source_ref"]
            ))
        return events

    def get_all_events(self) -> List[MemoryEvent]:
        query = "SELECT * FROM memory_events ORDER BY occurred_at ASC, ingested_at ASC"
        with self.get_connection() as conn:
            cursor = conn.execute(query)
            rows = cursor.fetchall()

        events = []
        for row in rows:
            events.append(MemoryEvent(
                event_id=row["event_id"],
                event_type=EventType(row["event_type"]),
                source_component=row["source_component"],
                application_id=row["application_id"],
                job_id=row["job_id"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                ingested_at=datetime.fromisoformat(row["ingested_at"]),
                payload=json.loads(row["payload_json"]),
                raw_source_ref=row["raw_source_ref"]
            ))
        return events

    def upsert_application_record(self, record: ApplicationRecord) -> None:
        query = """
            INSERT INTO application_records (
                application_id, job_id, company, role_title, status, created_at, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(application_id) DO UPDATE SET
                job_id = excluded.job_id,
                company = excluded.company,
                role_title = excluded.role_title,
                status = excluded.status,
                last_updated = excluded.last_updated
        """
        with self.get_connection() as conn:
            conn.execute(query, (
                record.application_id,
                record.job_id,
                record.company,
                record.role_title,
                record.status.value,
                record.created_at.isoformat(),
                record.last_updated.isoformat()
            ))
            conn.commit()

    def get_application_record(self, application_id: str) -> Optional[ApplicationRecord]:
        query = "SELECT * FROM application_records WHERE application_id = ?"
        with self.get_connection() as conn:
            cursor = conn.execute(query, (application_id,))
            row = cursor.fetchone()

        if not row:
            return None

        # Fetch linked event ids
        events = self.get_events_for_application(application_id)
        linked_ids = [e.event_id for e in events]

        return ApplicationRecord(
            application_id=row["application_id"],
            job_id=row["job_id"],
            company=row["company"],
            role_title=row["role_title"],
            status=ApplicationStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_updated=datetime.fromisoformat(row["last_updated"]),
            linked_event_ids=linked_ids
        )

    def list_application_records(self, status: Optional[ApplicationStatus] = None) -> List[ApplicationRecord]:
        if status is not None:
            query = "SELECT * FROM application_records WHERE status = ? ORDER BY last_updated DESC"
            params = (status.value,)
        else:
            query = "SELECT * FROM application_records ORDER BY last_updated DESC"
            params = ()

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        records = []
        for row in rows:
            app_id = row["application_id"]
            events = self.get_events_for_application(app_id)
            linked_ids = [e.event_id for e in events]
            records.append(ApplicationRecord(
                application_id=row["application_id"],
                job_id=row["job_id"],
                company=row["company"],
                role_title=row["role_title"],
                status=ApplicationStatus(row["status"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                last_updated=datetime.fromisoformat(row["last_updated"]),
                linked_event_ids=linked_ids
            ))
        return records

    def insert_status_transition(self, transition: StatusTransition) -> None:
        query = """
            INSERT INTO status_transitions (
                application_id, from_status, to_status, transitioned_at, triggering_event_id
            ) VALUES (?, ?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            conn.execute(query, (
                transition.application_id,
                transition.from_status.value if transition.from_status else None,
                transition.to_status.value,
                transition.transitioned_at.isoformat(),
                transition.triggering_event_id
            ))
            conn.commit()

    def clear_derived_tables(self) -> None:
        with self.get_connection() as conn:
            conn.execute("DELETE FROM status_transitions")
            conn.execute("DELETE FROM application_records")
            conn.commit()
