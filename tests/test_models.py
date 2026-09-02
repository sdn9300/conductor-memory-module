"""
Tests for Memory Module core data models (Phase 1).

Validates:
- Model creation with all fields
- Field validation and defaults
- DomainCooldown.from_rejection() factory
- generate_event_id() determinism
- EventType and ApplicationStatus enum completeness
"""

import pytest
from datetime import datetime, timezone, timedelta

from src.models import (
    EventType,
    ApplicationStatus,
    MemoryEvent,
    StatusTransition,
    ApplicationRecord,
    DomainCooldown,
    generate_event_id,
)


# ---------------------------------------------------------------------------
# EventType Enum
# ---------------------------------------------------------------------------

class TestEventType:
    def test_all_expected_members_exist(self):
        expected = {
            "JOB_DISCOVERED", "RESUME_TAILORED", "OUTREACH_SENT",
            "APPLICATION_SUBMITTED", "RESPONSE_CLASSIFIED",
            "INTERVIEW_SCHEDULED", "DOSSIER_COMPILED", "SKILL_GAP_EVALUATED",
            "MANUAL_NOTE", "UNKNOWN",
        }
        actual = {e.name for e in EventType}
        assert expected == actual, f"Missing: {expected - actual}, Extra: {actual - expected}"

    def test_string_values_are_lowercase(self):
        for e in EventType:
            assert e.value == e.value.lower()
            assert "_" in e.value or e.value == "unknown"


# ---------------------------------------------------------------------------
# ApplicationStatus Enum
# ---------------------------------------------------------------------------

class TestApplicationStatus:
    def test_all_expected_members_exist(self):
        expected = {
            "DISCOVERED", "TAILORED", "OUTREACHED", "APPLIED",
            "AWAITING_RESPONSE", "RESPONSE_RECEIVED", "INTERVIEW_SCHEDULED",
            "OFFER", "REJECTED", "GHOSTED", "WITHDRAWN",
            "AMBIGUOUS_OUTCOME", "UNKNOWN",
        }
        actual = {s.name for s in ApplicationStatus}
        assert expected == actual, f"Missing: {expected - actual}, Extra: {actual - expected}"


# ---------------------------------------------------------------------------
# MemoryEvent
# ---------------------------------------------------------------------------

class TestMemoryEvent:
    def test_basic_creation(self):
        now = datetime.now(timezone.utc)
        event = MemoryEvent(
            event_type=EventType.JOB_DISCOVERED,
            source_component="gleaner",
            application_id="app_001",
            job_id="job_001",
            candidate_id="sdn9300",
            domain="google.com",
            occurred_at=now,
            payload={"company": "Google", "role_title": "ML Engineer"},
            raw_source_ref="harvest_run_123",
        )
        assert event.event_type == EventType.JOB_DISCOVERED
        assert event.source_component == "gleaner"
        assert event.application_id == "app_001"
        assert event.job_id == "job_001"
        assert event.candidate_id == "sdn9300"
        assert event.domain == "google.com"
        assert event.occurred_at == now
        assert event.payload["company"] == "Google"
        assert event.raw_source_ref == "harvest_run_123"
        assert event.ingested_at is not None
        assert event.event_id is not None

    def test_optional_fields_default_to_none(self):
        event = MemoryEvent(
            event_type=EventType.MANUAL_NOTE,
            source_component="test",
            occurred_at=datetime.now(timezone.utc),
            payload={"note": "test note"},
        )
        assert event.application_id is None
        assert event.job_id is None
        assert event.candidate_id is None
        assert event.domain is None
        assert event.raw_source_ref is None

    def test_ingested_at_is_timezone_aware(self):
        event = MemoryEvent(
            event_type=EventType.UNKNOWN,
            source_component="test",
            occurred_at=datetime.now(timezone.utc),
            payload={},
        )
        assert event.ingested_at.tzinfo is not None

    def test_payload_preserves_nested_dicts(self):
        nested_payload = {
            "company": "DeepMind",
            "details": {"salary": 150000, "benefits": ["health", "stock"]},
            "tags": ["ml", "research"],
        }
        event = MemoryEvent(
            event_type=EventType.JOB_DISCOVERED,
            source_component="gleaner",
            occurred_at=datetime.now(timezone.utc),
            payload=nested_payload,
        )
        assert event.payload["details"]["salary"] == 150000
        assert "stock" in event.payload["details"]["benefits"]


# ---------------------------------------------------------------------------
# StatusTransition
# ---------------------------------------------------------------------------

class TestStatusTransition:
    def test_creation_with_from_status_none(self):
        transition = StatusTransition(
            application_id="app_001",
            from_status=None,
            to_status=ApplicationStatus.DISCOVERED,
            transitioned_at=datetime.now(timezone.utc),
            triggering_event_id="evt_001",
        )
        assert transition.from_status is None
        assert transition.to_status == ApplicationStatus.DISCOVERED

    def test_creation_with_both_statuses(self):
        transition = StatusTransition(
            application_id="app_001",
            from_status=ApplicationStatus.DISCOVERED,
            to_status=ApplicationStatus.TAILORED,
            transitioned_at=datetime.now(timezone.utc),
            triggering_event_id="evt_002",
        )
        assert transition.from_status == ApplicationStatus.DISCOVERED
        assert transition.to_status == ApplicationStatus.TAILORED


# ---------------------------------------------------------------------------
# ApplicationRecord
# ---------------------------------------------------------------------------

class TestApplicationRecord:
    def test_creation_with_all_fields(self):
        now = datetime.now(timezone.utc)
        record = ApplicationRecord(
            application_id="app_001",
            job_id="job_001",
            candidate_id="sdn9300",
            company="OpenAI",
            domain="openai.com",
            role_title="AI Engineer",
            status=ApplicationStatus.DISCOVERED,
            created_at=now,
            last_updated=now,
            linked_event_ids=["evt_001", "evt_002"],
        )
        assert record.application_id == "app_001"
        assert record.candidate_id == "sdn9300"
        assert record.domain == "openai.com"
        assert len(record.linked_event_ids) == 2

    def test_default_candidate_id(self):
        now = datetime.now(timezone.utc)
        record = ApplicationRecord(
            application_id="app_002",
            job_id="job_002",
            company="Meta",
            role_title="Data Scientist",
            status=ApplicationStatus.APPLIED,
            created_at=now,
            last_updated=now,
            linked_event_ids=[],
        )
        assert record.candidate_id == "sdn9300"

    def test_domain_defaults_to_none(self):
        now = datetime.now(timezone.utc)
        record = ApplicationRecord(
            application_id="app_003",
            job_id="job_003",
            company="Startup",
            role_title="Engineer",
            status=ApplicationStatus.DISCOVERED,
            created_at=now,
            last_updated=now,
            linked_event_ids=[],
        )
        assert record.domain is None


# ---------------------------------------------------------------------------
# DomainCooldown
# ---------------------------------------------------------------------------

class TestDomainCooldown:
    def test_from_rejection_factory(self):
        rejected_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        cooldown = DomainCooldown.from_rejection(
            domain="google.com",
            rejected_at=rejected_at,
            triggering_event_id="evt_rejection_001",
        )
        assert cooldown.domain == "google.com"
        assert cooldown.rejected_at == rejected_at
        assert cooldown.cooldown_expires_at == rejected_at + timedelta(days=30)
        assert cooldown.triggering_event_id == "evt_rejection_001"
        assert cooldown.is_active is True

    def test_from_rejection_custom_days(self):
        rejected_at = datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc)
        cooldown = DomainCooldown.from_rejection(
            domain="meta.com",
            rejected_at=rejected_at,
            triggering_event_id="evt_meta",
            cooldown_days=60,
        )
        assert cooldown.cooldown_expires_at == rejected_at + timedelta(days=60)

    def test_manual_creation(self):
        now = datetime.now(timezone.utc)
        cooldown = DomainCooldown(
            domain="netflix.com",
            rejected_at=now,
            cooldown_expires_at=now + timedelta(days=30),
            triggering_event_id="evt_netflix",
            is_active=False,
        )
        assert cooldown.is_active is False


# ---------------------------------------------------------------------------
# generate_event_id()
# ---------------------------------------------------------------------------

class TestGenerateEventId:
    def test_deterministic(self):
        id1 = generate_event_id("gleaner", "ref_001", "job_discovered", "2026-08-01T12:00:00+00:00")
        id2 = generate_event_id("gleaner", "ref_001", "job_discovered", "2026-08-01T12:00:00+00:00")
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = generate_event_id("gleaner", "ref_001", "job_discovered", "2026-08-01T12:00:00+00:00")
        id2 = generate_event_id("gleaner", "ref_002", "job_discovered", "2026-08-01T12:00:00+00:00")
        assert id1 != id2

    def test_length_is_32_hex(self):
        eid = generate_event_id("test", "ref", "unknown", "2026-01-01T00:00:00+00:00")
        assert len(eid) == 32
        assert all(c in "0123456789abcdef" for c in eid)
