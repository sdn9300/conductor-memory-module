"""
Memory Module — SQLite Persistence Layer (WAL Mode)

Implements MEM-AD-2.0 §5: 4-table schema, WAL journal mode, busy_timeout,
and all CRUD helpers for MemoryEvent, ApplicationRecord, StatusTransition,
and DomainCooldown.

ADR-1: SQLite with journal_mode=WAL and busy_timeout=5000ms.
"""

import sqlite3
import json
from contextlib import contextmanager
from typing import Generator, Optional, List
from datetime import datetime, timezone

from .models import (
    MemoryEvent,
    EventType,
    ApplicationRecord,
    ApplicationStatus,
    StatusTransition,
    DomainCooldown,
)


# ---------------------------------------------------------------------------
# Schema DDL — MEM-AD-2.0 §5
# ---------------------------------------------------------------------------

SCHEMA = """
-- IMMUTABLE SOURCE OF TRUTH (never updated, only inserted)
CREATE TABLE IF NOT EXISTS memory_events (
    event_id          TEXT PRIMARY KEY,
    event_type        TEXT NOT NULL,
    source_component  TEXT NOT NULL,
    application_id    TEXT,
    job_id            TEXT,
    candidate_id      TEXT,
    domain            TEXT,
    occurred_at       TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    payload_json      TEXT NOT NULL,
    raw_source_ref    TEXT
);

-- DERIVED MATERIALIZED VIEW (rebuildable via rebuild_derived_state())
CREATE TABLE IF NOT EXISTS application_records (
    application_id  TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL,
    candidate_id    TEXT NOT NULL DEFAULT 'sdn9300',
    company         TEXT NOT NULL,
    domain          TEXT,
    role_title      TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_updated    TEXT NOT NULL
);

-- TRANSITION AUDIT TRAIL (rebuildable)
CREATE TABLE IF NOT EXISTS status_transitions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id       TEXT NOT NULL,
    from_status          TEXT,
    to_status            TEXT NOT NULL,
    transitioned_at      TEXT NOT NULL,
    triggering_event_id  TEXT NOT NULL,
    FOREIGN KEY (application_id)      REFERENCES application_records(application_id),
    FOREIGN KEY (triggering_event_id) REFERENCES memory_events(event_id)
);

-- 30-DAY DOMAIN COOLDOWN REGISTRY
CREATE TABLE IF NOT EXISTS domain_cooldowns (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    domain               TEXT NOT NULL,
    rejected_at          TEXT NOT NULL,
    cooldown_expires_at  TEXT NOT NULL,
    triggering_event_id  TEXT NOT NULL,
    FOREIGN KEY (triggering_event_id) REFERENCES memory_events(event_id)
);

-- PERFORMANCE INDEXES
CREATE INDEX IF NOT EXISTS idx_events_application ON memory_events(application_id);
CREATE INDEX IF NOT EXISTS idx_events_type        ON memory_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_domain      ON memory_events(domain);
CREATE INDEX IF NOT EXISTS idx_events_occurred    ON memory_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_transitions_app    ON status_transitions(application_id);
CREATE INDEX IF NOT EXISTS idx_cooldowns_domain   ON domain_cooldowns(domain, cooldown_expires_at);
"""


class DatabaseHelper:
    """
    SQLite persistence layer for Memory Module.

    Connection configuration per ADR-1:
    - journal_mode=WAL (concurrent readers with single writer)
    - busy_timeout=5000ms (prevents SQLITE_BUSY on contention)
    - foreign_keys=ON (referential integrity)
    """

    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self._initialize_schema()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yields a configured SQLite connection with WAL mode and foreign keys."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _initialize_schema(self):
        """Create all tables and indexes if they don't exist."""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    # -------------------------------------------------------------------
    # MemoryEvent CRUD
    # -------------------------------------------------------------------

    def insert_memory_event(self, event: MemoryEvent) -> None:
        """Insert a single MemoryEvent. Raises on duplicate event_id (PRIMARY KEY)."""
        query = """
            INSERT INTO memory_events (
                event_id, event_type, source_component, application_id,
                job_id, candidate_id, domain, occurred_at, ingested_at,
                payload_json, raw_source_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            conn.execute(query, (
                event.event_id,
                event.event_type.value,
                event.source_component,
                event.application_id,
                event.job_id,
                event.candidate_id,
                event.domain,
                event.occurred_at.isoformat(),
                event.ingested_at.isoformat(),
                json.dumps(event.payload),
                event.raw_source_ref,
            ))
            conn.commit()

    def get_memory_event(self, event_id: str) -> Optional[MemoryEvent]:
        """Fetch a single MemoryEvent by event_id, or None if not found."""
        query = "SELECT * FROM memory_events WHERE event_id = ?"
        with self.get_connection() as conn:
            cursor = conn.execute(query, (event_id,))
            row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_memory_event(row)

    def get_events_for_application(self, application_id: str) -> List[MemoryEvent]:
        """Fetch all events for an application, ordered by occurred_at ASC."""
        query = "SELECT * FROM memory_events WHERE application_id = ? ORDER BY occurred_at ASC, ingested_at ASC"
        with self.get_connection() as conn:
            cursor = conn.execute(query, (application_id,))
            rows = cursor.fetchall()

        return [self._row_to_memory_event(row) for row in rows]

    def get_all_events(self) -> List[MemoryEvent]:
        """Fetch all events ordered by occurred_at ASC (for replay/rebuild)."""
        query = "SELECT * FROM memory_events ORDER BY occurred_at ASC, ingested_at ASC"
        with self.get_connection() as conn:
            cursor = conn.execute(query)
            rows = cursor.fetchall()

        return [self._row_to_memory_event(row) for row in rows]

    def _row_to_memory_event(self, row: sqlite3.Row) -> MemoryEvent:
        """Convert a database row to a MemoryEvent model."""
        return MemoryEvent(
            event_id=row["event_id"],
            event_type=EventType(row["event_type"]),
            source_component=row["source_component"],
            application_id=row["application_id"],
            job_id=row["job_id"],
            candidate_id=row["candidate_id"],
            domain=row["domain"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            ingested_at=datetime.fromisoformat(row["ingested_at"]),
            payload=json.loads(row["payload_json"]),
            raw_source_ref=row["raw_source_ref"],
        )

    # -------------------------------------------------------------------
    # ApplicationRecord CRUD
    # -------------------------------------------------------------------

    def upsert_application_record(self, record: ApplicationRecord) -> None:
        """Insert or update an ApplicationRecord (derived / materialized)."""
        query = """
            INSERT INTO application_records (
                application_id, job_id, candidate_id, company, domain,
                role_title, status, created_at, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(application_id) DO UPDATE SET
                job_id = excluded.job_id,
                candidate_id = excluded.candidate_id,
                company = excluded.company,
                domain = excluded.domain,
                role_title = excluded.role_title,
                status = excluded.status,
                last_updated = excluded.last_updated
        """
        with self.get_connection() as conn:
            conn.execute(query, (
                record.application_id,
                record.job_id,
                record.candidate_id,
                record.company,
                record.domain,
                record.role_title,
                record.status.value,
                record.created_at.isoformat(),
                record.last_updated.isoformat(),
            ))
            conn.commit()

    def get_application_record(self, application_id: str) -> Optional[ApplicationRecord]:
        """Fetch a single ApplicationRecord with linked event IDs."""
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
            candidate_id=row["candidate_id"],
            company=row["company"],
            domain=row["domain"],
            role_title=row["role_title"],
            status=ApplicationStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_updated=datetime.fromisoformat(row["last_updated"]),
            linked_event_ids=linked_ids,
        )

    def list_application_records(
        self,
        status: Optional[ApplicationStatus] = None,
        candidate_id: Optional[str] = None,
    ) -> List[ApplicationRecord]:
        """List ApplicationRecords, optionally filtered by status and/or candidate_id."""
        conditions = []
        params: list = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        if candidate_id is not None:
            conditions.append("candidate_id = ?")
            params.append(candidate_id)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM application_records{where_clause} ORDER BY last_updated DESC"

        with self.get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()

        records = []
        for row in rows:
            app_id = row["application_id"]
            events = self.get_events_for_application(app_id)
            linked_ids = [e.event_id for e in events]
            records.append(ApplicationRecord(
                application_id=row["application_id"],
                job_id=row["job_id"],
                candidate_id=row["candidate_id"],
                company=row["company"],
                domain=row["domain"],
                role_title=row["role_title"],
                status=ApplicationStatus(row["status"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                last_updated=datetime.fromisoformat(row["last_updated"]),
                linked_event_ids=linked_ids,
            ))
        return records

    # -------------------------------------------------------------------
    # StatusTransition CRUD
    # -------------------------------------------------------------------

    def insert_status_transition(self, transition: StatusTransition) -> None:
        """Insert a status transition audit record."""
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
                transition.triggering_event_id,
            ))
            conn.commit()

    # -------------------------------------------------------------------
    # DomainCooldown CRUD
    # -------------------------------------------------------------------

    def insert_domain_cooldown(self, cooldown: DomainCooldown) -> None:
        """Insert a 30-day domain cooldown record."""
        query = """
            INSERT INTO domain_cooldowns (
                domain, rejected_at, cooldown_expires_at, triggering_event_id
            ) VALUES (?, ?, ?, ?)
        """
        with self.get_connection() as conn:
            conn.execute(query, (
                cooldown.domain,
                cooldown.rejected_at.isoformat(),
                cooldown.cooldown_expires_at.isoformat(),
                cooldown.triggering_event_id,
            ))
            conn.commit()

    def get_active_cooldown(
        self,
        domain: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[DomainCooldown]:
        """
        Fetch the most recent active cooldown for a domain.

        Returns None if no active cooldown exists (i.e., cooldown_expires_at < as_of).
        """
        if as_of is None:
            as_of = datetime.now(timezone.utc)

        query = """
            SELECT * FROM domain_cooldowns
            WHERE domain = ? AND cooldown_expires_at > ?
            ORDER BY cooldown_expires_at DESC
            LIMIT 1
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, (domain, as_of.isoformat()))
            row = cursor.fetchone()

        if not row:
            return None

        return DomainCooldown(
            domain=row["domain"],
            rejected_at=datetime.fromisoformat(row["rejected_at"]),
            cooldown_expires_at=datetime.fromisoformat(row["cooldown_expires_at"]),
            triggering_event_id=row["triggering_event_id"],
            is_active=True,
        )

    def list_cooldowns(self, active_only: bool = True) -> List[DomainCooldown]:
        """List domain cooldowns, optionally filtered to active-only."""
        now_iso = datetime.now(timezone.utc).isoformat()

        if active_only:
            query = "SELECT * FROM domain_cooldowns WHERE cooldown_expires_at > ? ORDER BY cooldown_expires_at DESC"
            params: tuple = (now_iso,)
        else:
            query = "SELECT * FROM domain_cooldowns ORDER BY cooldown_expires_at DESC"
            params = ()

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        cooldowns = []
        for row in rows:
            expires_at = datetime.fromisoformat(row["cooldown_expires_at"])
            cooldowns.append(DomainCooldown(
                domain=row["domain"],
                rejected_at=datetime.fromisoformat(row["rejected_at"]),
                cooldown_expires_at=expires_at,
                triggering_event_id=row["triggering_event_id"],
                is_active=expires_at > datetime.now(timezone.utc),
            ))
        return cooldowns

    # -------------------------------------------------------------------
    # Maintenance
    # -------------------------------------------------------------------

    def clear_derived_tables(self) -> None:
        """Drop all derived state for rebuild. Preserves memory_events (source of truth)."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM status_transitions")
            conn.execute("DELETE FROM application_records")
            conn.execute("DELETE FROM domain_cooldowns")
            conn.commit()
