"""
Tests for Memory Module SQLite persistence layer (Phase 1).

Validates:
- WAL journal mode and busy_timeout=5000 are active (ADR-1)
- MemoryEvent round-trip with all fields including candidate_id/domain
- ApplicationRecord CRUD with new fields
- DomainCooldown insert / active query / list
- 4 tables and indexes exist
"""

import pytest
from datetime import datetime, timezone, timedelta
import sqlite3

from src.models import (
    MemoryEvent,
    EventType,
    ApplicationRecord,
    ApplicationStatus,
    StatusTransition,
    DomainCooldown,
)
from src.db import DatabaseHelper


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_memory.db"
    return DatabaseHelper(db_path=str(db_path))


# ---------------------------------------------------------------------------
# Schema & PRAGMA Tests
# ---------------------------------------------------------------------------

class TestSchemaAndPragmas:
    def test_wal_mode_is_active(self, test_db):
        """ADR-1: WAL journal mode must be active on every connection."""
        with test_db.get_connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.lower() == "wal"

    def test_busy_timeout_is_5000(self, test_db):
        """ADR-1: busy_timeout must be 5000ms to prevent SQLITE_BUSY."""
        with test_db.get_connection() as conn:
            cursor = conn.execute("PRAGMA busy_timeout")
            timeout = cursor.fetchone()[0]
            assert timeout == 5000

    def test_foreign_keys_enabled(self, test_db):
        with test_db.get_connection() as conn:
            cursor = conn.execute("PRAGMA foreign_keys")
            fk = cursor.fetchone()[0]
            assert fk == 1

    def test_all_four_tables_exist(self, test_db):
        """MEM-AD-2.0 §5: 4 tables must exist."""
        expected_tables = {"memory_events", "application_records", "status_transitions", "domain_cooldowns"}
        with test_db.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            actual_tables = {row[0] for row in cursor.fetchall()}
        assert expected_tables.issubset(actual_tables)

    def test_required_indexes_exist(self, test_db):
        expected_indexes = {
            "idx_events_application",
            "idx_events_type",
            "idx_events_domain",
            "idx_events_occurred",
            "idx_transitions_app",
            "idx_cooldowns_domain",
        }
        with test_db.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            actual_indexes = {row[0] for row in cursor.fetchall()}
        assert expected_indexes.issubset(actual_indexes)


# ---------------------------------------------------------------------------
# MemoryEvent Round-Trip Tests
# ---------------------------------------------------------------------------

class TestMemoryEventRoundTrip:
    def test_full_field_roundtrip(self, test_db):
        """Phase 1 exit criterion: MemoryEvent writes and reads back with 100% field parity."""
        event = MemoryEvent(
            event_id="test_roundtrip_001",
            event_type=EventType.JOB_DISCOVERED,
            source_component="gleaner",
            application_id="app_123",
            job_id="job_456",
            candidate_id="sdn9300",
            domain="google.com",
            occurred_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            ingested_at=datetime(2026, 8, 1, 12, 0, 1, tzinfo=timezone.utc),
            payload={"url": "https://example.com/job", "salary_estimate": 120000},
            raw_source_ref="harvest_run_abc",
        )

        # Insert
        test_db.insert_memory_event(event)

        # Read back
        retrieved = test_db.get_memory_event("test_roundtrip_001")
        assert retrieved is not None

        # Check every field
        assert retrieved.event_id == event.event_id
        assert retrieved.event_type == event.event_type
        assert retrieved.source_component == event.source_component
        assert retrieved.application_id == event.application_id
        assert retrieved.job_id == event.job_id
        assert retrieved.candidate_id == event.candidate_id
        assert retrieved.domain == event.domain
        assert retrieved.occurred_at == event.occurred_at
        assert retrieved.ingested_at == event.ingested_at
        assert retrieved.payload == event.payload
        assert retrieved.raw_source_ref == event.raw_source_ref

    def test_nested_payload_survives_roundtrip(self, test_db):
        """Nested dicts/lists in payload must survive JSON serialization."""
        nested_payload = {
            "details": {"salary": 150000, "benefits": ["health", "stock"]},
            "tags": ["ml", "research"],
        }
        event = MemoryEvent(
            event_id="test_nested_001",
            event_type=EventType.JOB_DISCOVERED,
            source_component="gleaner",
            occurred_at=datetime.now(timezone.utc),
            payload=nested_payload,
        )
        test_db.insert_memory_event(event)
        retrieved = test_db.get_memory_event("test_nested_001")
        assert retrieved.payload["details"]["salary"] == 150000
        assert "stock" in retrieved.payload["details"]["benefits"]

    def test_missing_event_returns_none(self, test_db):
        assert test_db.get_memory_event("non_existent_id") is None

    def test_candidate_id_and_domain_nullable(self, test_db):
        """candidate_id and domain should be nullable."""
        event = MemoryEvent(
            event_id="test_nullable_001",
            event_type=EventType.MANUAL_NOTE,
            source_component="test",
            occurred_at=datetime.now(timezone.utc),
            payload={"note": "test"},
        )
        test_db.insert_memory_event(event)
        retrieved = test_db.get_memory_event("test_nullable_001")
        assert retrieved.candidate_id is None
        assert retrieved.domain is None

    def test_get_events_for_application(self, test_db):
        for i in range(3):
            event = MemoryEvent(
                event_id=f"app_events_{i}",
                event_type=EventType.JOB_DISCOVERED,
                source_component="test",
                application_id="app_multi",
                occurred_at=datetime(2026, 8, 1, 12, i, 0, tzinfo=timezone.utc),
                payload={"seq": i},
            )
            test_db.insert_memory_event(event)

        events = test_db.get_events_for_application("app_multi")
        assert len(events) == 3
        # Verify ordering by occurred_at ASC
        for i, ev in enumerate(events):
            assert ev.payload["seq"] == i


# ---------------------------------------------------------------------------
# ApplicationRecord CRUD Tests
# ---------------------------------------------------------------------------

class TestApplicationRecordCrud:
    def test_upsert_and_get(self, test_db):
        # Need an event first for linked_event_ids lookup
        event = MemoryEvent(
            event_id="evt_for_record",
            event_type=EventType.JOB_DISCOVERED,
            source_component="gleaner",
            application_id="app_record_001",
            candidate_id="sdn9300",
            domain="meta.com",
            occurred_at=datetime.now(timezone.utc),
            payload={},
        )
        test_db.insert_memory_event(event)

        record = ApplicationRecord(
            application_id="app_record_001",
            job_id="job_record_001",
            candidate_id="sdn9300",
            company="Meta",
            domain="meta.com",
            role_title="ML Engineer",
            status=ApplicationStatus.DISCOVERED,
            created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
            linked_event_ids=["evt_for_record"],
        )
        test_db.upsert_application_record(record)

        retrieved = test_db.get_application_record("app_record_001")
        assert retrieved is not None
        assert retrieved.candidate_id == "sdn9300"
        assert retrieved.domain == "meta.com"
        assert retrieved.company == "Meta"

    def test_upsert_updates_existing(self, test_db):
        now = datetime.now(timezone.utc)
        event = MemoryEvent(
            event_id="evt_upsert",
            event_type=EventType.JOB_DISCOVERED,
            source_component="test",
            application_id="app_upsert",
            occurred_at=now,
            payload={},
        )
        test_db.insert_memory_event(event)

        record = ApplicationRecord(
            application_id="app_upsert",
            job_id="job_upsert",
            candidate_id="sdn9300",
            company="Before",
            role_title="Dev",
            status=ApplicationStatus.DISCOVERED,
            created_at=now,
            last_updated=now,
            linked_event_ids=["evt_upsert"],
        )
        test_db.upsert_application_record(record)

        # Update
        record.status = ApplicationStatus.TAILORED
        record.company = "After"
        test_db.upsert_application_record(record)

        retrieved = test_db.get_application_record("app_upsert")
        assert retrieved.status == ApplicationStatus.TAILORED
        assert retrieved.company == "After"


# ---------------------------------------------------------------------------
# DomainCooldown CRUD Tests
# ---------------------------------------------------------------------------

class TestDomainCooldownCrud:
    def test_insert_and_get_active(self, test_db):
        # Need a triggering event for FK
        event = MemoryEvent(
            event_id="evt_cooldown_trigger",
            event_type=EventType.RESPONSE_CLASSIFIED,
            source_component="sentiment_classifier",
            occurred_at=datetime.now(timezone.utc),
            payload={},
        )
        test_db.insert_memory_event(event)

        rejected_at = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        cooldown = DomainCooldown.from_rejection(
            domain="google.com",
            rejected_at=rejected_at,
            triggering_event_id="evt_cooldown_trigger",
        )
        test_db.insert_domain_cooldown(cooldown)

        # Query within cooldown window
        active = test_db.get_active_cooldown(
            "google.com",
            as_of=datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert active is not None
        assert active.domain == "google.com"
        assert active.is_active is True

    def test_cooldown_expires_after_30_days(self, test_db):
        event = MemoryEvent(
            event_id="evt_cooldown_expired",
            event_type=EventType.RESPONSE_CLASSIFIED,
            source_component="test",
            occurred_at=datetime.now(timezone.utc),
            payload={},
        )
        test_db.insert_memory_event(event)

        rejected_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        cooldown = DomainCooldown.from_rejection(
            domain="expired.com",
            rejected_at=rejected_at,
            triggering_event_id="evt_cooldown_expired",
        )
        test_db.insert_domain_cooldown(cooldown)

        # Query after 30 days (day 31)
        expired = test_db.get_active_cooldown(
            "expired.com",
            as_of=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert expired is None

    def test_cooldown_active_on_day_29(self, test_db):
        event = MemoryEvent(
            event_id="evt_cooldown_day29",
            event_type=EventType.RESPONSE_CLASSIFIED,
            source_component="test",
            occurred_at=datetime.now(timezone.utc),
            payload={},
        )
        test_db.insert_memory_event(event)

        rejected_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        cooldown = DomainCooldown.from_rejection(
            domain="day29.com",
            rejected_at=rejected_at,
            triggering_event_id="evt_cooldown_day29",
        )
        test_db.insert_domain_cooldown(cooldown)

        # Query on day 29
        active = test_db.get_active_cooldown(
            "day29.com",
            as_of=datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert active is not None

    def test_no_cooldown_for_unknown_domain(self, test_db):
        result = test_db.get_active_cooldown("unknown.com")
        assert result is None

    def test_list_cooldowns(self, test_db):
        for i, domain in enumerate(["a.com", "b.com"]):
            event = MemoryEvent(
                event_id=f"evt_list_cd_{i}",
                event_type=EventType.RESPONSE_CLASSIFIED,
                source_component="test",
                occurred_at=datetime.now(timezone.utc),
                payload={},
            )
            test_db.insert_memory_event(event)

            cooldown = DomainCooldown.from_rejection(
                domain=domain,
                rejected_at=datetime.now(timezone.utc),
                triggering_event_id=f"evt_list_cd_{i}",
            )
            test_db.insert_domain_cooldown(cooldown)

        all_cooldowns = test_db.list_cooldowns(active_only=False)
        assert len(all_cooldowns) == 2
