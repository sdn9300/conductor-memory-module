"""
FastMCP Server exposing Memory Module tools for the CareerOS ecosystem.
Reference: MEM-AD-2.0 §6 (FastMCP Tool Mesh API Surface) & MEM-IP-2.0 Phase 6
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastmcp import FastMCP

from src.models import EventType, ApplicationStatus, MemoryEvent, ApplicationRecord
from src.store import MemoryStore

# Global store instance (configurable via create_mcp_server)
_store = MemoryStore()

mcp = FastMCP(
    name="conductor-memory-module",
    instructions=(
        "FastMCP tool interface for CareerOS Component #8 (Memory Module & Learning Layer). "
        "Provides immutable event-sourced state storage, application history tracking, "
        "30-day domain cooldown verification, stale application detection, and state rebuilds."
    ),
)


@mcp.tool()
def record_event(
    event_type: str,
    source_component: str,
    application_id: Optional[str] = None,
    job_id: Optional[str] = None,
    candidate_id: Optional[str] = "sdn9300",
    domain: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    raw_source_ref: Optional[str] = None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Record an immutable MemoryEvent into the append-only event ledger.

    Automatically derives application state, transitions, and 30-day domain cooldowns.
    Idempotent: duplicate events with identical hash are confirmed no-ops (ADR-5).
    """
    try:
        norm_type = EventType(event_type.lower().strip())
    except ValueError:
        norm_type = EventType.UNKNOWN

    if occurred_at:
        try:
            dt_occurred = datetime.fromisoformat(occurred_at)
        except Exception:
            dt_occurred = datetime.now(timezone.utc)
    else:
        dt_occurred = datetime.now(timezone.utc)

    event = MemoryEvent(
        event_type=norm_type,
        source_component=source_component,
        application_id=application_id,
        job_id=job_id,
        candidate_id=candidate_id or "sdn9300",
        domain=domain,
        occurred_at=dt_occurred,
        payload=payload or {},
        raw_source_ref=raw_source_ref,
    )

    _store.record_event(event)

    app_record = _store.get_application(application_id) if application_id else None
    return {
        "status": "success",
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "application_id": event.application_id,
        "current_status": app_record.status.value if app_record else None,
        "occurred_at": event.occurred_at.isoformat(),
    }


@mcp.tool()
def get_application(application_id: str) -> Dict[str, Any]:
    """Retrieve current materialized state for a single job application."""
    record = _store.get_application(application_id)
    if record is None:
        return {"error": f"Application with ID '{application_id}' not found."}
    return record.model_dump(mode="json")


@mcp.tool()
def list_applications(
    status: Optional[str] = None,
    candidate_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List application records, optionally filtered by status and/or candidate_id."""
    filter_status = None
    if status:
        try:
            filter_status = ApplicationStatus(status.lower().strip())
        except ValueError:
            pass

    records = _store.list_applications(status=filter_status, candidate_id=candidate_id)
    return [r.model_dump(mode="json") for r in records]


@mcp.tool()
def get_history(application_id: str) -> List[Dict[str, Any]]:
    """Retrieve full chronological event history (occurred_at ASC) for an application."""
    events = _store.get_history(application_id)
    return [e.model_dump(mode="json") for e in events]


@mcp.tool()
def get_stale_applications(days_silent: int = 7) -> List[Dict[str, Any]]:
    """Find in-progress applications with no activity for >= days_silent days (GHOSTED detection)."""
    stale_records = _store.get_stale_applications(days_silent=days_silent)
    return [r.model_dump(mode="json") for r in stale_records]


@mcp.tool()
def check_domain_cooldown(domain: str) -> Dict[str, Any]:
    """Check whether a company or ATS domain is under active 30-day rejection cooldown.

    Returns {"domain": str, "is_blocked": bool, "cooldown_expires_at": str | None}
    """
    res = _store.check_domain_cooldown(domain)
    expires_str = (
        res["cooldown_expires_at"].isoformat()
        if res["cooldown_expires_at"]
        else None
    )
    return {
        "domain": domain,
        "is_blocked": res["is_blocked"],
        "cooldown_expires_at": expires_str,
    }


@mcp.tool()
def rebuild_derived_state() -> Dict[str, Any]:
    """Drop and replay derived tables from the immutable memory_events stream.

    Reconstitutes application_records, status_transitions, and domain_cooldowns (Gate G5).
    """
    _store.rebuild_derived_state()
    total_apps = len(_store.list_applications())
    return {
        "status": "success",
        "message": f"Rebuild complete. Derived state reconstituted for {total_apps} application(s).",
        "total_applications": total_apps,
    }


def create_mcp_server(store: Optional[MemoryStore] = None) -> FastMCP:
    """Factory creating an MCP server instance with a custom storage backend."""
    global _store
    if store is not None:
        _store = store
    return mcp


def main() -> None:
    """CLI entrypoint to run the Memory Module FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
