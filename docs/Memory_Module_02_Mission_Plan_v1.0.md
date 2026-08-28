# Memory Module — Mission Plan & Strategic Constitution

**CONDUCTOR / UNIFIED CAREEROS Subsystem #8 · Learning & State Layer**  
**Document ID:** `MEM-MP-2.0` · **Version:** 2.0 · **Status:** Approved Strategic Directive  
**Date:** August 28, 2026  
**System Owner:** Soumyadeep Nath  
**Governance Anchor:** Law 8 (Memory Event Sourcing & Immutability — "Remember; Do Not Decide")  
**Related Documents:** `MEM-PS-2.0` (Problem Statement), `MEM-AD-2.0` (Architecture Design), `MEM-IP-2.0` (Implementation Plan)

---

## 1. Core Mission Statement

To engineer a bulletproof, append-only, event-sourced state ledger and FastMCP query mesh for the Unified CareerOS ecosystem.

Memory Module guarantees that every lifecycle event—from initial job discovery through resume tailoring, recruiter outreach, ATS auto-submission, recruiter email triage, and interview scheduling—is immutably persisted, hash-deduplicated, and materialized into high-speed derived application state.

### The Three Inviolable Tenets

1. **Absolute Completeness (No Silent Drops):** Every event emitted by an upstream sub-agent (The Harvester, AlignResume, Overture, PDF Auto-Apply, Sentiment Classifier, MCP Chief of Staff) is captured with its full raw payload preserved, even when malformed or unrecognized (`UNKNOWN` bucket).
2. **Mathematical Replay Parity (Event Sourcing):** Derived application state is 100% deterministic and rebuildable from the raw event stream. Replaying 10,000 events via `rebuild_derived_state()` produces identical state with zero byte drift.
3. **Subsystem Independence & Zero Token Cost:** Memory Module operates as an independent, deterministic FastMCP service. Ingestion, state transitions, deduplication, and SQL queries execute with **zero LLM and zero embedding calls**, ensuring maximum speed, zero cost, and total immunity from model hallucinations.

---

## 2. Strategic & Functional Objectives

```
+---------------------------------------------------------------------------------------------------+
|                                 STRATEGIC & FUNCTIONAL OBJECTIVES                                 |
|                                                                                                   |
|  [OBJ-1] Immutable Event Ledger    ──► Ingest and store all sub-agent events in SQLite WAL mode   |
|  [OBJ-2] FastMCP Service Mesh       ──► Expose typed tools for sibling agents and Conductor DAG    |
|  [OBJ-3] 30-Day Cooldown Engine     ──► Block duplicate applications within 30-day domain windows  |
|  [OBJ-4] Deterministic State Engine ──► Pure Python state machine with 100% transition coverage    |
|  [OBJ-5] Instant Interview Prep CLI ──► Sub-second audit trail of resume diffs and outreach copy   |
|  [OBJ-6] RAG Foundation Capstone    ──► Structured data foundation for future Qdrant vector memory  |
+---------------------------------------------------------------------------------------------------+
```

### 2.1 Functional Objectives
- **F-OBJ-1:** Provide high-throughput, atomic event ingestion via `record_event()` with sub-10ms write latency.
- **F-OBJ-2:** Enforce deterministic deduplication via cryptographic hash `event_id` generation (ADR-5).
- **F-OBJ-3:** Materialize and query live application state (`get_application`, `list_applications`, `get_history`).
- **F-OBJ-4:** Identify stalled applications with customizable inactivity windows (`get_stale_applications(days_silent)`).
- **F-OBJ-5:** Track company-level domain rejections and enforce automated 30-day application cooldowns (`check_domain_cooldown(domain)`).
- **F-OBJ-6:** Provide a full replay engine (`rebuild_derived_state()`) for database recovery, schema migration, and test parity.

### 2.2 Strategic CareerOS Objectives
- **S-OBJ-1:** Unblock the **Conductor Master DAG Coordinator [0]** by providing an authoritative ground-truth state provider.
- **S-OBJ-2:** Integrate **Sentiment Classifier [9]** outputs (`interview_invite`, `rejection`, `info_request`) into permanent application records.
- **S-OBJ-3:** Safeguard candidate professional reputation by preventing spam and duplicate submissions across ATS platforms.
- **S-OBJ-4:** Demonstrate enterprise-grade backend engineering patterns (Event Sourcing, CQRS, FastMCP, SQLite WAL concurrency) in the developer portfolio.

---

## 3. Scope Boundaries: v1.0 / v2.0 vs. Deferred Roadmap

| In-Scope for Current Build (v1.0 / v2.0) | Explicitly Deferred to Future Capstones |
|---|---|
| Pydantic v2 event and record schemas (`MemoryEvent`, `ApplicationRecord`) | Semantic / vector natural language search (Qdrant RAG) |
| SQLite local database with WAL mode and `busy_timeout=5000ms` | Cloud-hosted PostgreSQL / DynamoDB distributed databases |
| FastMCP Server interface (stdio / JSON-RPC / SSE bindings) | Multi-tenant authentication and role-based access control |
| Pure Python deterministic state-machine transition logic | Machine-learning predictive application outcome modeling |
| Full event replay parity (`rebuild_derived_state()`) | Live browser execution or ATS form scraping (PDF Auto-Apply owns this) |
| CLI inspection, debugging, and dogfooding harness | Autonomous email dispatch or calendar booking (Chief of Staff owns this) |
| Automated 30-day domain cooldown validation engine | Distributed event streaming buses (Kafka / RabbitMQ) |

---

## 4. Ecosystem Governance & Law Alignment

Memory Module enforces and complies with the **8 Governance Laws of CareerOS**:

1. **Law 1 (Universal Human Gate):** Memory Module records human approval tokens and status updates (`MANUAL_NOTE`), ensuring no automated agent acts without state authorization.
2. **Law 3 (FastMCP Tool Mesh):** All inter-agent communication occurs over standard Model Context Protocol tool endpoints.
3. **Law 4 (Single Source of Truth):** Memory Module references `candidate_id` as an opaque foreign key to **Candidate Profile JSON [10]**, never mutating or duplicating profile facts.
4. **Law 6 (No-Silent-Drop & Degrade):** Every event ingestion attempt produces a persisted record. Unparseable payloads fall back to `UNKNOWN` with full raw payloads preserved.
5. **Law 8 (Memory Event Sourcing & "Remember; Do Not Decide"):** Core storage is strictly append-only; derived views are materialized; Memory Module never decides next routing actions.

---

## 5. Minimum Viable Start (MVS)

To validate the core architecture with zero external blockers, Memory Module defines an immediate three-step verification loop:

```
+---------------------------------------------------------------------------------------------------+
|                                    MINIMUM VIABLE START (MVS)                                     |
|                                                                                                   |
|  [Step 1] Ingest 4 Lifecycle Events:                                                              |
|           1. JOB_DISCOVERED        (Google - Senior Backend Engineer)                             |
|           2. RESUME_TAILORED       (Diff: 4 bullets modified for Distributed Systems)             |
|           3. APPLICATION_SUBMITTED (Greenhouse ATS submission receipt)                            |
|           4. RESPONSE_CLASSIFIED   (Sentiment: interview_invite, Urgency: 0.95)                   |
|                                                                                                   |
|  [Step 2] Assert Derived State:                                                                   |
|           status == "interview_scheduled", last_updated == timestamp(4), total_events == 4        |
|                                                                                                   |
|  [Step 3] Execute Full Replay:                                                                    |
|           Drop derived tables, run rebuild_derived_state(), assert 100% identical state           |
+---------------------------------------------------------------------------------------------------+
```

---

## 6. Definition of Done (DoD) for v2.0 Release

Memory Module v2.0 is considered production-ready when:

- [ ] **Hard Gate G1 Passed:** 100% zero data loss across process crashes and restarts.
- [ ] **Hard Gate G2 Passed:** Deterministic idempotency verified against 1,000 duplicate event bursts.
- [ ] **Hard Gate G3 Passed:** Malformed and future-version schemas cleanly captured in `UNKNOWN` fallback bucket.
- [ ] **Hard Gate G4 Passed:** 100% of state-machine transitions verified with query latency < 50ms.
- [ ] **Hard Gate G5 Passed:** `rebuild_derived_state()` produces 100% byte-for-byte state parity across 5,000 randomized event histories.
- [ ] **Hard Gate G6 Passed:** Multi-threaded SQLite lock contention test passes with 10 concurrent readers/writers under WAL mode without `database locked` errors.
- [ ] **30-Day Cooldown Engine Verified:** `check_domain_cooldown()` successfully blocks re-applications to rejected domains within 30 days.
- [ ] **FastMCP Tool Mesh Complete:** All 7 MCP tools (`record_event`, `get_application`, `list_applications`, `get_history`, `get_stale_applications`, `rebuild_derived_state`, `check_domain_cooldown`) tested and documented.
- [ ] **Repo Hygiene Confirmed:** `.gitignore` protects SQLite database files from accidental Git commits.
