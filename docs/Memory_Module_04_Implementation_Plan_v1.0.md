# Memory Module — Phase-wise Implementation Plan

**CONDUCTOR / UNIFIED CAREEROS Subsystem #8 · Learning & State Layer**  
**Document ID:** `MEM-IP-2.0` · **Version:** 2.0 · **Status:** Approved  
**Date:** August 28, 2026  
**System Owner:** Soumyadeep Nath  
**Governance Anchor:** Law 8 (Memory Event Sourcing & Immutability)  
**Related:** `MEM-AD-2.0`, `MEM-EP-2.0`, `CAREEROS-PHASE-v2.1`

---

## 1. Unified CareerOS Phase Alignment

Memory Module implementation maps onto the broader **Unified CareerOS Phase-wise Roadmap**:

| CareerOS Phase | Memory Module Contribution |
|---|---|
| **Phase 2: Profile & Memory Core** | Phases 0–3 below (foundations, data model, ingestion, query API) |
| **Phase 3: Application Execution** | Phase 4 (CLI harness + PDF Auto-Apply adapter integration) |
| **Phase 5: Auto-Apply & Memory Sync** | Phase 5 (full test suite, 30-day cooldown hardening, v2.0 packaging) |
| **Phase 6+: Conductor Integration** | Phase 6 (deferred — FastMCP server live with Conductor DAG) |

---

## 2. Phase Overview Table

| Phase | Objective | Estimated Effort | Gates / Exit Criteria |
|---|---|---|---|
| **0** | Environment setup, repo scaffolding, `.gitignore` hardening | 2–3 hrs | Imports pass; `.gitignore` verified before first commit |
| **1** | Core Pydantic data models + SQLite WAL schema | 4–6 hrs | All 4 tables exist; `MemoryEvent` round-trips without field loss |
| **2** | `record_event()` ingestion API + state machine + producer adapters | 6–8 hrs | All state transitions pass; idempotency confirmed; adapters reconciled |
| **3** | Full `MemoryStore` query API + `rebuild_derived_state()` | 4–6 hrs | Rebuild parity test passes (Gate G5); `get_stale_applications()` correct |
| **4** | `check_domain_cooldown()` + 30-day cooldown engine | 3–4 hrs | Cooldown blocks re-application within 30 days (verified by test) |
| **5** | CLI harness for debugging and interview-prep queries | 2–3 hrs | MVS query (`stale --days N`) correct against hand-built test data |
| **6** | FastMCP Server wrapper (all 7 tools exposed as MCP endpoints) | 4–5 hrs | All tools callable by Conductor via MCP client; integration test passes |
| **7** | Full test suite + edge cases + hardening + v2.0 packaging | 5–7 hrs | Gates G1–G6 all pass; DoD checklist in `MEM-MP-2.0` §6 fully checked |
| **8 (deferred)** | Qdrant RAG layer, PostgreSQL migration, multi-user | Not estimated | Triggered by DevOps Phase 14 / Agentic AI Stage 03 capstone |

**Total Phases 0–7: ~30–42 hours** (~4 weeks at 8–10 focused hours/week alongside IIT Roorkee coursework).  
Phases are strictly sequential; each exit gate is a hard prerequisite for the next phase.

---

## 3. Phase 0 — Foundations & Environment Setup

**Objective:** Repository scaffold, dependency confirmation, security baseline.

**Deliverables:**
- Repository initialized (or `memory_module/` subdirectory within CONDUCTOR monorepo).
- `pyproject.toml` / `requirements.txt`: `pydantic>=2`, `pytest`, `fastmcp`; `sqlite3` needs no install (stdlib).
- `.gitignore` entry for `*.db`, `*.sqlite`, `memory.db` — added **before** the first commit, not retroactively.
- Six-document specification suite copied into `/docs` per spec-anchored operating model.
- `src/__init__.py`, `tests/__init__.py` scaffold.

**Exit Criteria:**
- [ ] `import pydantic, sqlite3, pytest, fastmcp` succeeds in the target environment.
- [ ] `.gitignore` confirmed to exclude SQLite database files before any data commit.

---

## 4. Phase 1 — Core Data Models & Persistence Layer

**Objective:** Implement schemas and tables from `MEM-AD-2.0` §3 and §5; nothing wired to producers yet.

**Deliverables:**
- `src/models.py`: `EventType`, `ApplicationStatus`, `MemoryEvent`, `StatusTransition`, `ApplicationRecord`, `DomainCooldown` as Pydantic v2 models.
- `src/db.py`: SQLite schema creation (4 tables + indexes from `MEM-AD-2.0` §5), connection helper with WAL mode + busy_timeout, basic insert/select helpers.
- `tests/test_models.py`: `MemoryEvent` round-trips correctly through the database (write → read → identical object).

**Exit Criteria:**
- [ ] All 4 tables created with correct constraints and indexes.
- [ ] `MemoryEvent` with a nested `payload` dict writes and reads back with 100% field parity.
- [ ] WAL mode and `busy_timeout=5000ms` confirmed active via `PRAGMA` assertions.

---

## 5. Phase 2 — Ingestion API, State Machine & Producer Adapters

**Objective:** Implement `record_event()` + state machine + adapters per producer from `MEM-AD-2.0` §7.

**Deliverables:**
- `src/state_machine.py`: Pure function `apply_event(current_status: ApplicationStatus | None, event: MemoryEvent) -> ApplicationStatus`, implementing the full transition table from `MEM-AD-2.0` §4, including `UNKNOWN` event no-op.
- `src/store.py` — `MemoryStore.record_event()`: validates event type, deduplicates by `event_id` (ADR-5 hash), writes to `memory_events`, derives and writes resulting `application_records` / `status_transitions`.
- Producer adapters in `src/adapters/`:
  - `from_harvester_event(raw: dict) -> MemoryEvent`
  - `from_align_resume_event(tailoring_run: dict) -> MemoryEvent`
  - `from_overture_event(run_record: dict) -> MemoryEvent`
  - `from_classified_signal(signal: dict) -> MemoryEvent`
  - `from_auto_apply_receipt(receipt: dict) -> MemoryEvent`
  - `from_chief_of_staff_event(event: dict) -> MemoryEvent`

**Reconciliation Task (NOT optional before Phase 2 closes):**  
The `ClassifiedSignalIngest` schema proposed in `MEM-AD-2.0` §7 must be verified against Sentiment Classifier's actual v1.0.1 output schema. If field names differ, the adapter must be corrected. This task is the named explicit gap — leaving it unresolved means the integration is unverified, not merely incomplete.

**Exit Criteria:**
- [ ] Every (from_status, event_type) pair in the state-machine table has at least one passing pytest assertion.
- [ ] Re-submitting an identical `event_id` is confirmed to be a no-op (zero duplicate rows, derived state unchanged).
- [ ] `ClassifiedSignal` reconciliation task closed; adapter corrected or confirmed.

---

## 6. Phase 3 — Full Query API & Rebuild Engine

**Objective:** Implement the complete read-side of `MemoryStore` from `MEM-AD-2.0` §6.

**Deliverables:**
- `get_application(application_id)`, `list_applications(status, candidate_id)`, `get_history(application_id)`, `get_stale_applications(days_silent)` implemented against derived tables.
- `rebuild_derived_state()`: drops `application_records`, `status_transitions`, replays all events from `memory_events` ordered by `occurred_at ASC`.
- `tests/test_replay.py`: Build state incrementally via `record_event()` calls across a 20-event realistic application lifecycle, capture the result, call `rebuild_derived_state()` from empty tables, and assert 100% byte-for-byte equivalence.

**Exit Criteria:**
- [ ] All 4 read methods return correct results against a hand-constructed test dataset with out-of-order event delivery (EC-MEM-A02).
- [ ] Rebuild equivalence test (`rebuild_derived_state()` vs. incremental) passes — this is Evaluation Gate G5.
- [ ] Query latency for `list_applications()` on 10,000+ events < 50ms (Gate G4 monitoring).

---

## 7. Phase 4 — 30-Day Domain Cooldown Engine

**Objective:** Implement the `domain_cooldowns` table and `check_domain_cooldown()` FastMCP tool to block duplicate applications within 30 days of rejection.

**Deliverables:**
- `src/cooldown.py`: Logic for recording domain rejections in `domain_cooldowns` when a `REJECTED` status transition is materialized. Cooldown calculated as `rejected_at + 30 days`.
- `check_domain_cooldown(domain: str) -> dict` method on `MemoryStore`: returns `{is_blocked: bool, cooldown_expires_at: datetime | None}`.
- `tests/test_cooldown.py`: Simulate rejection → immediate re-query → assert `is_blocked=True`; advance clock past 30 days → assert `is_blocked=False`.
- Integration with `record_event()`: on `REJECTED` transition, automatically write cooldown record.

**Exit Criteria:**
- [ ] `check_domain_cooldown("google.com")` returns `is_blocked=True` within 30 days of a recorded rejection.
- [ ] `check_domain_cooldown("google.com")` returns `is_blocked=False` on day 31+.
- [ ] Cooldown records are included in `rebuild_derived_state()` replay.

---

## 8. Phase 5 — CLI Harness (Interview Prep & Debug Interface)

**Objective:** Give Memory Module a usable human interface before Conductor exists, per MVS in `MEM-MP-2.0` §5.

**Deliverables:**
- `memory_cli.py` (or `python -m memory_module`) supporting:
  - `record <event-json>` — inject a test event from JSON
  - `status <application_id>` — current status + last updated
  - `stale --days N` — applications silent for N+ days (the MVS query)
  - `history <application_id>` — full ordered event trail with timestamp and source component
  - `cooldown --domain <domain>` — check 30-day rejection cooldown status
  - `rebuild` — trigger `rebuild_derived_state()` and report parity

**Exit Criteria:**
- [ ] `stale --days N` correctly answers the MVS query against manually entered test data.
- [ ] CLI requires no other CareerOS component to be running.
- [ ] `cooldown` and `rebuild` commands complete with no exceptions.

---

## 9. Phase 6 — FastMCP Server Wrapper

**Objective:** Expose all 7 `MemoryStore` methods as standard MCP tool endpoints for Conductor and sibling sub-agents.

**Deliverables:**
- `src/mcp_server.py`: FastMCP Server wrapping all 7 tools with typed MCP schemas:
  - `record_event`, `get_application`, `list_applications`, `get_history`
  - `get_stale_applications`, `check_domain_cooldown`, `rebuild_derived_state`
- MCP server launch script (`run_mcp_server.py`) with stdio and SSE transport options.
- Integration test: Conductor-compatible MCP client calls `get_application(app_id)` over stdio and receives a valid `ApplicationRecord` JSON response.

**Exit Criteria:**
- [ ] All 7 tools callable by an external MCP client over stdio transport.
- [ ] MCP tool schemas validated against FastMCP contract definitions.
- [ ] Server starts cleanly within 2 seconds; responds to tool calls within 50ms (local).

---

## 10. Phase 7 — Full Test Suite, Hardening & v2.0 Packaging

**Objective:** Close all remaining Evaluation Gates, cover Edge Case Plan Categories A–F, and ship v2.0.

**Deliverables:**
- Full `pytest` suite (target: 100% of hard-blocking gates G1–G6 passing):
  - `test_durability.py` — Gate G1: process crash and restart, event persistence
  - `test_idempotency.py` — Gate G2: 1,000 duplicate event bursts, zero double-writes
  - `test_fallback.py` — Gate G3: malformed and future-version schema capture
  - `test_state_machine.py` — Gate G4: full transition table + sub-50ms latency
  - `test_replay.py` — Gate G5: incremental vs. rebuild parity (already in Phase 3)
  - `test_concurrency.py` — Gate G6: 10 concurrent readers/writers, zero SQLite lock errors
- At least one test per Edge Case Plan (`MEM-EC-2.0`) scenario in Categories A–F.
- `README.md` documenting: API surface, state machine diagram, 30-day cooldown, CLI usage, FastMCP tool catalog.
- Version tag `v2.0`.

**Exit Criteria:**
- [ ] Gates G1–G6 all pass in automated `pytest` suite.
- [ ] All 6 edge case categories have at least one test.
- [ ] Definition of Done checklist in `MEM-MP-2.0` §6 fully checked.

---

## 11. Phase 8 — Deferred / Future Roadmap

Not scheduled as part of this implementation plan. Listed for continuity with `MEM-AD-2.0` §10:

| Deferred Extension | Trigger |
|---|---|
| Qdrant semantic/vector RAG layer | DevOps Phase 14 / Agentic AI Stage 03 capstone start |
| PostgreSQL migration | Concurrent-writer contention becomes real (EC-MEM-E01) |
| Multi-candidate / SaaS support | CareerOS transitions from single-user to team deployment |
| Automated staleness sweep / scheduler | Conductor needs push-style stale notifications |

---

## 12. Dependency Graph

```
Phase 0 (Setup)
    └── Phase 1 (Models & Schema)
            └── Phase 2 (Ingestion + State Machine) ── requires: Sentiment Classifier schema reconciliation
                    └── Phase 3 (Query API + Rebuild)
                            ├── Phase 4 (Cooldown Engine)
                            └── Phase 5 (CLI Harness)
                                    └── Phase 6 (FastMCP Server)
                                            └── Phase 7 (Full Test Suite + v2.0 Ship)
```

No Memory Module phase blocks The Gleaner's or PDF Auto-Apply Agent's own implementation — their integration adapters are written against proposed contracts now and corrected later without restructuring Memory Module, by design (ADR-2's extensibility NFR).
