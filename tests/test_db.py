import pytest
from datetime import datetime, timezone
import os

from src.models import MemoryEvent, EventType
from src.db import DatabaseHelper

@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_memory.db"
    return DatabaseHelper(db_path=str(db_path))

def test_memory_event_roundtrip(test_db):
    event = MemoryEvent(
        event_type=EventType.JOB_DISCOVERED,
        source_component="harvester",
        application_id="app_123",
        job_id="job_456",
        occurred_at=datetime.now(timezone.utc),
        payload={"url": "https://example.com/job", "salary_estimate": 120000},
        raw_source_ref="harvest_run_abc"
    )

    # Insert
    test_db.insert_memory_event(event)

    # Read back
    retrieved_event = test_db.get_memory_event(event.event_id)
    assert retrieved_event is not None
    
    # Check fields
    assert retrieved_event.event_id == event.event_id
    assert retrieved_event.event_type == event.event_type
    assert retrieved_event.source_component == event.source_component
    assert retrieved_event.application_id == event.application_id
    assert retrieved_event.job_id == event.job_id
    assert retrieved_event.occurred_at == event.occurred_at
    assert retrieved_event.ingested_at == event.ingested_at
    assert retrieved_event.payload == event.payload
    assert retrieved_event.raw_source_ref == event.raw_source_ref

def test_missing_memory_event_returns_none(test_db):
    assert test_db.get_memory_event("non_existent_id") is None
