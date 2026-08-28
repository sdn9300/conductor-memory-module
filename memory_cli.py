#!/usr/bin/env python3
"""
CONDUCTOR [8] - Memory Module CLI Harness (Phase 4)
Standalone CLI interface for inspecting, recording, and querying application memory.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Optional

from src.models import EventType, ApplicationStatus, MemoryEvent
from src.store import MemoryStore

def get_store(db_path: str = "memory.db") -> MemoryStore:
    return MemoryStore(db_path=db_path)

def cmd_record(args, store: MemoryStore) -> None:
    payload = {}
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"Error parsing --payload JSON: {e}", file=sys.stderr)
            sys.exit(1)

    if args.company:
        payload["company"] = args.company
    if args.role:
        payload["role_title"] = args.role
    if args.status_override:
        payload["status_override"] = args.status_override
    if args.intent:
        payload["intent_label"] = args.intent

    try:
        event_type = EventType(args.event_type)
    except ValueError:
        print(f"Invalid event type '{args.event_type}'. Valid types: {[e.value for e in EventType]}", file=sys.stderr)
        sys.exit(1)

    event = MemoryEvent(
        event_type=event_type,
        source_component=args.source or "manual_cli",
        application_id=args.application_id,
        job_id=args.job_id,
        occurred_at=datetime.now(timezone.utc),
        payload=payload,
        raw_source_ref=args.raw_ref or "cli_manual_entry"
    )

    store.record_event(event)
    print(f"Successfully recorded event {event.event_id} ({event.event_type.value}) for application: {event.application_id or 'N/A'}")
    
    if event.application_id:
        app = store.get_application(event.application_id)
        if app:
            print(f"Current Status: {app.status.value.upper()} | Company: {app.company} | Role: {app.role_title}")

def cmd_status(args, store: MemoryStore) -> None:
    app = store.get_application(args.application_id)
    if not app:
        print(f"No application found with ID '{args.application_id}'.", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print(f"APPLICATION STATUS: {app.application_id}")
    print("=" * 60)
    print(f"  Company:          {app.company}")
    print(f"  Role Title:       {app.role_title}")
    print(f"  Job ID:           {app.job_id}")
    print(f"  Current Status:   {app.status.value.upper()}")
    print(f"  Created At:       {app.created_at.isoformat()}")
    print(f"  Last Activity:    {app.last_updated.isoformat()}")
    print(f"  Linked Events:    {len(app.linked_event_ids)}")
    print("=" * 60)

def cmd_list(args, store: MemoryStore) -> None:
    filter_status = None
    if args.status:
        try:
            filter_status = ApplicationStatus(args.status)
        except ValueError:
            print(f"Invalid status '{args.status}'. Valid statuses: {[s.value for s in ApplicationStatus]}", file=sys.stderr)
            sys.exit(1)

    apps = store.list_applications(status=filter_status)
    if not apps:
        print("No applications found.")
        return

    print(f"{'APPLICATION ID':<20} | {'STATUS':<20} | {'COMPANY':<20} | {'ROLE':<25} | {'LAST UPDATED'}")
    print("-" * 105)
    for app in apps:
        print(f"{app.application_id:<20} | {app.status.value:<20} | {app.company:<20} | {app.role_title:<25} | {app.last_updated.strftime('%Y-%m-%d %H:%M')}")

def cmd_stale(args, store: MemoryStore) -> None:
    days = args.days
    stale_apps = store.get_stale_applications(days_silent=days)

    print("=" * 105)
    print(f"STALE APPLICATIONS (Awaiting response, silent for >= {days} days)")
    print("=" * 105)

    if not stale_apps:
        print(f"No stale applications found (no applications silent >= {days} days).")
        return

    print(f"{'APPLICATION ID':<20} | {'STATUS':<20} | {'COMPANY':<20} | {'ROLE':<25} | {'LAST ACTIVITY'}")
    print("-" * 105)
    for app in stale_apps:
        print(f"{app.application_id:<20} | {app.status.value:<20} | {app.company:<20} | {app.role_title:<25} | {app.last_updated.strftime('%Y-%m-%d %H:%M')}")

def cmd_history(args, store: MemoryStore) -> None:
    history = store.get_history(args.application_id)
    if not history:
        print(f"No history found for application ID '{args.application_id}'.", file=sys.stderr)
        return

    print("=" * 90)
    print(f"EVENT HISTORY FOR APPLICATION: {args.application_id} ({len(history)} events)")
    print("=" * 90)

    for i, event in enumerate(history, 1):
        print(f"[{i}] {event.occurred_at.strftime('%Y-%m-%d %H:%M:%S UTC')} | Type: {event.event_type.value} | Source: {event.source_component}")
        print(f"    Event ID: {event.event_id}")
        if event.payload:
            payload_str = json.dumps(event.payload, indent=6)
            print(f"    Payload:\n{payload_str}")
        print("-" * 90)

def cmd_rebuild(args, store: MemoryStore) -> None:
    print("Rebuilding derived application records and status transitions from raw events...")
    store.rebuild_derived_state()
    total_apps = len(store.list_applications())
    print(f"Rebuild complete! Derived state reconstituted for {total_apps} application(s).")

def main():
    parser = argparse.ArgumentParser(
        description="CONDUCTOR Memory Module CLI Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", default="memory.db", help="Path to SQLite database file (default: memory.db)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. record
    p_record = subparsers.add_parser("record", help="Record a new MemoryEvent")
    p_record.add_argument("-a", "--app-id", dest="application_id", help="Application ID")
    p_record.add_argument("-t", "--type", dest="event_type", required=True, help="Event type (e.g. job_discovered, outreach_sent, etc.)")
    p_record.add_argument("-s", "--source", dest="source", default="cli_manual", help="Source component name")
    p_record.add_argument("-j", "--job-id", dest="job_id", help="Job ID")
    p_record.add_argument("-c", "--company", dest="company", help="Company name")
    p_record.add_argument("-r", "--role", dest="role", help="Role title")
    p_record.add_argument("--intent", dest="intent", help="Intent label (for response_classified)")
    p_record.add_argument("--status-override", dest="status_override", help="Status override (for manual_note)")
    p_record.add_argument("-p", "--payload", dest="payload", help="JSON payload string")
    p_record.add_argument("--raw-ref", dest="raw_ref", help="Raw source reference identifier")

    # 2. status
    p_status = subparsers.add_parser("status", help="Get status of an application")
    p_status.add_argument("application_id", help="Application ID")

    # 3. list
    p_list = subparsers.add_parser("list", help="List applications")
    p_list.add_argument("--status", help="Filter by ApplicationStatus (optional)")

    # 4. stale
    p_stale = subparsers.add_parser("stale", help="Find stale applications awaiting response")
    p_stale.add_argument("--days", type=int, default=7, help="Number of days silent (default: 7)")

    # 5. history
    p_history = subparsers.add_parser("history", help="Get event history for an application")
    p_history.add_argument("application_id", help="Application ID")

    # 6. rebuild
    p_rebuild = subparsers.add_parser("rebuild", help="Rebuild derived state by replaying all events")

    args = parser.parse_args()
    store = get_store(db_path=args.db)

    commands = {
        "record": cmd_record,
        "status": cmd_status,
        "list": cmd_list,
        "stale": cmd_stale,
        "history": cmd_history,
        "rebuild": cmd_rebuild,
    }

    commands[args.command](args, store)

if __name__ == "__main__":
    main()
