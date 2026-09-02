# Memory Module — Architecture Design

**CONDUCTOR / UNIFIED CAREEROS Subsystem #8 · Learning & State Layer**  
**Document ID:** `MEM-AD-2.0` · **Version:** 2.0 · **Status:** Approved  
**Date:** August 28, 2026  
**System Owner:** Soumyadeep Nath  
**Governance Anchor:** Law 8 (Memory Event Sourcing & Immutability)  
**Related:** `MEM-PS-2.0`, `MEM-MP-2.0`, `MEM-IP-2.0`, `MEM-EP-2.0`, `MEM-EC-2.0`

---

## 1. Design Principles

Four principles govern every decision in this document:

1. **No-Silent-Drop (Law 6):** Every event passed to `record_event()` produces a persisted artifact in `memory_events`. Malformed or unrecognized events fall into the `UNKNOWN` bucket — full raw payload preserved, `event_type` flagged, ingestion does not raise.
2. **Zero LLM in the Critical Path (Law 2):** Core ingestion, deduplication, state transitions, and SQL queries are 100% deterministic Python and SQL. Zero token cost, zero hallucination risk, zero latency degradation from model calls.
3. **FastMCP Tool Mesh (Law 3):** All sibling sub-agent interactions with Memory Module occur exclusively over typed MCP tool endpoints. No internal SQLite files or Python internals are directly accessed by peers.
4. **Remember; Do Not Decide (Law 8):** Memory Module materializes derived *state* (what happened, what is true now) and enforces mechanical rules (30-day cooldowns, idempotency). It never derives *actions* — all routing decisions belong exclusively to Conductor [0].

---

## 2. System Context Diagram

```
+--------------------------------------------------------------------------------------------------------+
|                                       CAREEROS MEMORY MODULE [8]                                       |
|                                                                                                        |
|   UPSTREAM PRODUCERS                       FASTMCP TOOL MESH                 DOWNSTREAM CONSUMERS     |
|   ──────────────────                       ──────────────────                 ───────────────────────  |
|                                                                                                        |
|   [1] The Gleaner          JOB_DISCOVERED ──────────────────────────────►  [0] Conductor DAG         |
|   [2] AlignResume            RESUME_TAILORED ─────► ┌──────────────────┐ ──► (State & Cooldowns)       |
|   [3] Overture Outreach      OUTREACH_SENT ──────► │  record_event()   │                              |
|   [4] Research Agent         DOSSIER_COMPILED ───► │  get_application()│     [CLI Harness]             |
|   [5] Future-Fit             SKILL_GAP_EVAL ─────► │  list_applications│     (Debug & Interview Prep)  |
|   [6] MCP Chief of Staff     INTERVIEW_SCHED ────► │  get_history()    │                              |
|   [7] PDF Auto-Apply         APPLICATION_SUB ────► │  get_stale_apps() │     [Future: Qdrant RAG]      |
|   [9] Sentiment Classifier   RESPONSE_CLASS ─────► │  rebuild_state()  │     (Semantic recall layer)   |
|                                                   │  check_cooldown() │                              |
|                                                   └──────────┬───────┘                               |
|                                                              │                                        |
|                              ┌───────────────────────────────▼────────────────────────────────────┐  |
|                              │                      SQLite DATABASE (WAL Mode)                    │  |
|                              │                                                                    │  |
|                              │  ┌─────────────────────────────────────────────────────────────┐  │  |
|                              │  │  memory_events        (Append-Only Immutable Source of Truth)│  │  |
|                              │  └─────────────────────────────────────────────────────────────┘  │  |
|                              │           │ derives via state machine                               │  |
|                              │  ┌────────▼──────────────┐  ┌───────────────────────────────────┐  │  |
|                              │  │  application_records   │  │  status_transitions               │  │  |
|                              │  │  (Materialized View)   │  │  (Transition Audit Trail)         │  │  |
|                              │  └────────────────────────┘  └───────────────────────────────────┘  │  |
|                              │  ┌─────────────────────────────────────────────────────────────┐  │  |
|                              │  │  domain_cooldowns      (30-Day Rejection Cooldown Registry)  │  │  |
|                              │  └─────────────────────────────────────────────────────────────┘  │  |
|                              └────────────────────────────────────────────────────────────────────┘  |
+--------------------------------------------------------------------------------------------------------+
```

---

## 3. Data Models (Pydantic v2)

```python
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from typing import Any, Optional
import hashlib, json

class EventType(str, Enum):
    JOB_DISCOVERED        = "job_discovered"
    RESUME_TAILORED       = "resume_tailored"
    OUTREACH_SENT         = "outreach_sent"
    APPLICATION_SUBMITTED = "application_submitted"
    RESPONSE_CLASSIFIED   = "response_classified"
    INTERVIEW_SCHEDULED   = "interview_scheduled"
    DOSSIER_COMPILED      = "dossier_compiled"
    SKILL_GAP_EVALUATED   = "skill_gap_evaluated"
    MANUAL_NOTE           = "manual_note"
    UNKNOWN               = "unknown"  # Fallback — never reject an event

class ApplicationStatus(str, Enum):
    DISCOVERED         = "discovered"
    TAILORED           = "tailored"
    OUTREACHED         = "outreached"
    APPLIED            = "applied"
    AWAITING_RESPONSE  = "awaiting_response"
    RESPONSE_RECEIVED  = "response_received"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    OFFER              = "offer"
    REJECTED           = "rejected"
    GHOSTED            = "ghosted"      # Computed at query time — not event-driven
    WITHDRAWN          = "withdrawn"
    AMBIGUOUS_OUTCOME  = "ambiguous_outcome"
    UNKNOWN            = "unknown"

class MemoryEvent(BaseModel):
    """Append-only. Source of truth. Never mutated after write."""
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Deterministic hash for idempotency: hash(source+ref+type)"
    )
    event_type: EventType
    source_component: str               # e.g. "sentiment_classifier", "pdf_auto_apply"
    application_id: Optional[str] = None
    job_id: Optional[str] = None
    candidate_id: Optional[str] = None  # Opaque FK to Candidate Profile JSON [10]
    domain: Optional[str] = None        # ATS/company domain for cooldown tracking
    occurred_at: datetime               # Producer-reported wall-clock time
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any]             # Schema-on-read; validated per-type at boundary
    raw_source_ref: Optional[str] = None  # e.g. originating ClassifiedSignal ID

class StatusTransition(BaseModel):
    application_id: str
    from_status: Optional[ApplicationStatus]  # Null for the creating (first) event
    to_status: ApplicationStatus
    transitioned_at: datetime
    triggering_event_id: str

class ApplicationRecord(BaseModel):
    """Derived / materialized. Rebuildable from memory_events at any time."""
    application_id: str
    job_id: str
    candidate_id: str
    company: str
    domain: Optional[str]
    role_title: str
    status: ApplicationStatus
    created_at: datetime
    last_updated: datetime
    linked_event_ids: list[str]

class DomainCooldown(BaseModel):
    """30-day rejection cooldown per company domain."""
    domain: str
    rejected_at: datetime
    cooldown_expires_at: datetime       # = rejected_at + 30 days
    triggering_event_id: str
    is_active: bool                     # Computed at query time
```

---

## 4. State Machine Transition Table

| From Status | Triggering Event | To Status | Notes |
|---|---|---|---|
| *(none)* | `JOB_DISCOVERED` | `DISCOVERED` | Creates the `ApplicationRecord` |
| `DISCOVERED` | `RESUME_TAILORED` | `TAILORED` | |
| `TAILORED` | `OUTREACH_SENT` | `OUTREACHED` | |
| `TAILORED` | `APPLICATION_SUBMITTED` | `APPLIED` | Direct-apply path (skips outreach) |
| `OUTREACHED` | `APPLICATION_SUBMITTED` | `APPLIED` | |
| `APPLIED` / `OUTREACHED` | `RESPONSE_CLASSIFIED` (interview_invite) | `INTERVIEW_SCHEDULED` | |
| `APPLIED` / `OUTREACHED` | `RESPONSE_CLASSIFIED` (rejection) | `REJECTED` | Triggers 30-day domain cooldown |
| `APPLIED` / `OUTREACHED` | `RESPONSE_CLASSIFIED` (ambiguous) | `AMBIGUOUS_OUTCOME` | Held for manual review |
| `INTERVIEW_SCHEDULED` | `RESPONSE_CLASSIFIED` (offer) | `OFFER` | |
| `INTERVIEW_SCHEDULED` | `RESPONSE_CLASSIFIED` (rejection) | `REJECTED` | Post-interview rejection |
| *any non-terminal* | *(computed, not event-driven)* | `GHOSTED` | Inferred when N days silence elapsed |
| *any* | `MANUAL_NOTE` with explicit status override | *(as specified)* | Human correction escape hatch |
| *any* | `UNKNOWN` event type | *(unchanged)* | Logged in full; status untouched; flagged |

**Soft-Terminal States:** `REJECTED`, `OFFER`, `WITHDRAWN` are soft-terminal — reversible only via explicit `MANUAL_NOTE`, never by automatic transition. This handles recruiter reversals (EC-MEM-C03).

**GHOSTED State:** Computed at `get_stale_applications()` query time by calculating elapsed days since `last_updated`. Not event-driven, breaking the pure event-trigger pattern by design — see Edge Case EC-MEM-C04.

---

## 5. SQLite Storage Schema (WAL Mode)

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

-- IMMUTABLE SOURCE OF TRUTH (never updated, only inserted)
CREATE TABLE IF NOT EXISTS memory_events (
    event_id          TEXT PRIMARY KEY,
    event_type        TEXT NOT NULL,
    source_component  TEXT NOT NULL,
    application_id    TEXT,
    job_id            TEXT,
    candidate_id      TEXT,
    domain            TEXT,
    occurred_at       TEXT NOT NULL,   -- ISO 8601 UTC
    ingested_at       TEXT NOT NULL,   -- ISO 8601 UTC
    payload_json      TEXT NOT NULL,   -- Full raw payload always preserved
    raw_source_ref    TEXT
);

-- DERIVED MATERIALIZED VIEW (rebuildable via rebuild_derived_state())
CREATE TABLE IF NOT EXISTS application_records (
    application_id  TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL,
    candidate_id    TEXT NOT NULL,
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
```

---

## 6. FastMCP Tool Mesh API Surface

All 7 FastMCP tools form the complete public contract for Memory Module. Sibling sub-agents call these tools; they never access the SQLite file directly.

```python
class MemoryStore:
    # ─── Write (Ingestion) ─────────────────────────────────────────────────
    def record_event(self, event: MemoryEvent) -> None:
        """Append event to memory_events; derive state; enforce cooldown on REJECTED.
        Idempotent: duplicate event_id is a confirmed no-op (ADR-5)."""
        ...

    # ─── Read (Query) ──────────────────────────────────────────────────────
    def get_application(self, application_id: str) -> ApplicationRecord | None:
        """Fetch current materialized state for a single application."""
        ...

    def list_applications(
        self,
        status: ApplicationStatus | None = None,
        candidate_id: str | None = None
    ) -> list[ApplicationRecord]:
        """List all applications, optionally filtered by status or candidate."""
        ...

    def get_history(self, application_id: str) -> list[MemoryEvent]:
        """Full ordered event trail for an application (occurred_at ASC)."""
        ...

    def get_stale_applications(self, days_silent: int) -> list[ApplicationRecord]:
        """Applications with no new events for >= days_silent days (GHOSTED detection)."""
        ...

    def check_domain_cooldown(self, domain: str) -> dict:
        """Returns {is_blocked: bool, cooldown_expires_at: datetime | None}
        for the 30-day rejection cooldown on a company domain."""
        ...

    # ─── Maintenance ───────────────────────────────────────────────────────
    def rebuild_derived_state(self) -> None:
        """Drop and replay application_records, status_transitions from
        memory_events in occurred_at order. Used for recovery, migration,
        and evaluation gate G5 parity verification."""
        ...
```

---

## 7. Integration Contracts per Producer

| Producer | Event Type | Key Payload Fields | Reconciliation Status |
|---|---|---|---|
| **The Gleaner [1]** | `JOB_DISCOVERED` | `job_id`, `company`, `role_title`, `domain`, `source_url`, `jd_hash` | Proposed — reconcile against Gleaner spec before Phase 2 |
| **AlignResume [2]** | `RESUME_TAILORED` | `tailoring_run_id`, `resume_diff_summary`, `bullets_added`, `bullets_removed` | Proposed — maps from `TailoringRun` model |
| **Overture Outreach [3]** | `OUTREACH_SENT` | `recipient_email`, `channel`, `subject`, `overture_run_id` | Proposed — maps from Overture SQLite run history |
| **Research Agent [4]** | `DOSSIER_COMPILED` | `dossier_id`, `company`, `tech_stack`, `financial_health_score` | Proposed — maps from Research Agent output schema |
| **Future-Fit [5]** | `SKILL_GAP_EVALUATED` | `opportunity_cost_score`, `skill_delta`, `gap_summary` | Proposed — maps from Future-Fit evaluation output |
| **MCP Chief of Staff [6]** | `INTERVIEW_SCHEDULED` | `calendar_event_id`, `interviewer`, `scheduled_at`, `platform` | Proposed — maps from CalendarEngine event model |
| **PDF Auto-Apply [7]** | `APPLICATION_SUBMITTED` | `ats_domain`, `submission_id`, `form_fields_filled`, `pdf_artifact_path` | Proposed — maps from Usher submission receipt |
| **Sentiment Classifier [9]** | `RESPONSE_CLASSIFIED` | `source_email_ref`, `urgency_score`, `recommended_action`, `sentiment_category`, `classified_at` | **Reconcile before Phase 2** — EC-AMBIG-010 history |

**Design Rule for Sentiment Classifier:** Memory Module treats `urgency_score` and `recommended_action` as *advisory metadata*, never as sole authority for automatic terminal state transitions. Full raw signal is always retained in `payload_json`. This directly addresses Sentiment Classifier's known EC-AMBIG-010 defect (deadline language inflating urgency in rejection emails) — retaining raw signals enables future Sentiment Classifier recalibrations to be replayed retroactively via `rebuild_derived_state()`.

---

## 8. Architecture Decision Records (ADRs)

### ADR-1: SQLite as Storage Engine (WAL Mode)

**Status:** Accepted · **Date:** Aug 27, 2026

**Decision:** SQLite with `journal_mode=WAL` and `busy_timeout=5000ms`.

**Rationale:**
- Zero infrastructure overhead (standard library `sqlite3`, no server process)
- Proven in Overture [3] at equivalent single-candidate scale
- WAL mode enables concurrent readers with a single writer, supporting CLI + Conductor simultaneous access
- Full SQL query capability for complex joins and filtered reads

**Consequence:** If Conductor introduces high-frequency concurrent writes (>50/sec), migration to PostgreSQL becomes necessary. Explicit trigger condition documented in EC-MEM-E01.

---

### ADR-2: Structured Ledger vs. Semantic/Vector Memory for v1.0

**Status:** Accepted · **Date:** Aug 27, 2026

**Decision:** v1.0/v2.0 ships a deterministic event ledger only. Qdrant RAG is explicitly deferred.

**Rationale:** Conductor's v1.0 needs require precise structured state queries (`WHERE status='applied' AND domain='google.com'`), not fuzzy natural-language recall. Building the vector layer now would: (a) duplicate infrastructure scheduled as a deliberate four-way capstone build, and (b) violate Mission Plan's warning against "learning tools in isolation."

**Consequence:** The structured event ledger becomes the exact corpus the future RAG layer will ingest — forward-compatible groundwork, not wasted work.

---

### ADR-3: In-Process Python API vs. HTTP Service (FastMCP as Primary Interface)

**Status:** Accepted · **Date:** Aug 27, 2026

**Decision:** Expose `MemoryStore` as both a directly importable Python class (for CLI and local testing) and a FastMCP Server (for cross-agent MCP tool invocations).

**Rationale:** FastMCP aligns with Law 3 (standard tool mesh across all CareerOS agents). The in-process import is retained for CLI harness and unit testing without requiring a running server.

**Consequence:** Business logic is fully transport-agnostic. Adding SSE or WebSocket transport in v3.0 requires no changes to core `MemoryStore` implementation.

---

### ADR-4: Event Sourcing Hybrid (Append-Only Log + Derived Materialized Views)

**Status:** Accepted · **Date:** Aug 27, 2026

**Decision:** `memory_events` is the append-only source of truth. `application_records` and `status_transitions` are derived, rebuildable materializations.

**Rationale:**
- Complete audit trail: every derived fact traces to the exact triggering event(s)
- Bug recovery: state-machine patches can be applied retroactively by replaying history
- Performance: fast current-state queries via derived table without scanning event stream

**Consequence:** The state-machine transition function must be pure and deterministic — same event sequence in, identical derived state out, always. This is directly tested by Evaluation Gate G5.

---

### ADR-5: Deterministic `event_id` for Idempotency

**Status:** Accepted · **Date:** Aug 27, 2026

**Decision:** `event_id` is generated as `sha256(source_component + raw_source_ref + event_type + occurred_at)`. `record_event()` is a confirmed no-op if `event_id` already exists in `memory_events`.

**Rationale:** Upstream producers (Overture, Sentiment Classifier) may retry on network failures without knowing whether the first attempt succeeded. Deterministic IDs guarantee natural collision on retries.

**Consequence:** Producers must implement deterministic `event_id` generation. Documented as an explicit contract expectation in §7 Integration Contracts.

---

## 9. Security & Privacy Controls

The database will contain real recruiter names, email fragments, company-outcome data, and compensation details. Given CareerOS repositories may be partially public:

| Control | Implementation |
|---|---|
| **SQLite File `.gitignore`** | Added in Phase 0, before first commit — structural prevention, not retroactive cleanup |
| **Payload Excerpting** | Producers should store references or short excerpts, not full email bodies, in `payload_json` |
| **No Credentials in Payloads** | Explicit contract expectation: no API keys, tokens, or auth headers inside event payloads |
| **Domain-Level Privacy** | `domain` field stores normalized company domains (e.g., `google.com`), not personal recruiter emails |

---

## 10. Future Extension Points (Explicitly Deferred)

| Extension | Trigger Condition |
|---|---|
| Qdrant semantic/vector layer | DevOps Phase 14 / Agentic AI Stage 03 RAG Capstone begins |
| FastAPI REST wrapper | Conductor deployed as a genuinely separate network service |
| PostgreSQL migration | Concurrent-writer contention becomes real, not hypothetical (EC-MEM-E01) |
| Automated staleness sweeper | Conductor needs push-style notification rather than pull-on-query |
| Multi-candidate support | CareerOS transitions from single-user to SaaS deployment model |
