# Memory Module — Evaluation Plan

**CONDUCTOR / UNIFIED CAREEROS Subsystem #8 · Learning & State Layer**  
**Document ID:** `MEM-EP-2.0` · **Version:** 2.0 · **Status:** Approved  
**Date:** August 28, 2026  
**System Owner:** Soumyadeep Nath  
**Governance Anchor:** Law 8 (Memory Event Sourcing & Immutability)  
**Related:** `MEM-AD-2.0`, `MEM-IP-2.0`, `MEM-EC-2.0`

---

## 1. Evaluation Philosophy

Consistent with the tiered gate structure used across Unified CareerOS:

- **Hard-blocking gates (G1–G6):** Deterministically testable correctness properties that must pass before v2.0 ships. No exceptions.
- **Monitoring gates (M1–M3):** Quality signals worth tracking but that never block a release on their own.

Because Memory Module's core logic is fully deterministic (Law 2 — zero LLM in the critical path), its testing pyramid is unit-test-heavy compared to Sentiment Classifier's. A state machine either transitions correctly or it doesn't; there is no probabilistic calibration to evaluate.

**Six gates (vs. five in v1.0):** Gate G6 (SQLite Concurrency) was added to the hard-blocking set to account for the FastMCP server enabling concurrent read/write access from Conductor, CLI, and other sub-agents — a new operational risk not present in the original single-process design.

---

## 2. Evaluation Dimensions

| Dimension | What It Verifies |
|---|---|
| **Durability** | No event is lost across process restart, crash, or disk flush delay |
| **Idempotency** | Duplicate event delivery never corrupts state or double-counts records |
| **Fallback Coverage** | Every event type — including unrecognized schema versions — produces a persisted artifact |
| **Correctness** | State-machine transitions match the table in `MEM-AD-2.0` §4 exactly |
| **Replay Parity** | Derived state always equals what a full replay of `memory_events` would produce |
| **Concurrency Safety** | Concurrent SQLite readers/writers under WAL mode produce zero data corruption |
| **Cooldown Enforcement** | 30-day domain rejection cooldowns are correctly recorded and queried |

---

## 3. Test Strategy

Following the standard pyramid, weighted toward the base given the deterministic core:

- **Unit tests (majority):** Every cell of the state-transition table gets at least one test — `(from_status, event_type) → (to_status)`. Schema validation tests confirm that malformed payloads produce a persisted `MemoryEvent` with `event_type = UNKNOWN` rather than raising.
- **Integration tests:** Simulated end-to-end lifecycle: `JOB_DISCOVERED → RESUME_TAILORED → APPLICATION_SUBMITTED → RESPONSE_CLASSIFIED (interview_invite)`, asserting `status = INTERVIEW_SCHEDULED` and `get_history()` returns all four events in `occurred_at` order.
- **Property-style replay test (ADR-4 proof):** Build a 20-event non-trivial history via `record_event()`, capture `application_records`, call `rebuild_derived_state()` from empty, assert byte-for-byte identical result. This is the empirical proof that event-sourcing delivers its promise.
- **Concurrency stress test (Gate G6):** Spawn 10 threads — 5 concurrent writers, 5 concurrent readers — against a shared SQLite WAL database for 60 seconds. Assert zero `database locked` errors and zero data corruption.
- **Manual dogfooding (MVS):** The Phase 5 CLI harness run against realistic test data answering the `stale --days N` query from `MEM-MP-2.0` §5.

---

## 4. Hard-Blocking Evaluation Gates (G1–G6)

> [!IMPORTANT]
> All six gates must pass before v2.0 ships. A component whose entire purpose is being a trustworthy record cannot have a known gap in any of the six.

| Gate | Full Name | Requirement | Verifies |
|---|---|---|---|
| **G1** | Zero Data Loss | Every event passed to `record_event()` is retrievable via `get_history()` after a fresh process start. Verified after a simulated crash (SIGKILL mid-write). | Durability |
| **G2** | Deterministic Idempotency | Re-submitting 1,000 identical `event_id` bursts produces zero duplicate rows and zero change to derived state. | Idempotency |
| **G3** | Fallback Coverage | A malformed payload and an unrecognized `event_type` are each written to `memory_events` as `UNKNOWN` rather than raising an exception or being silently dropped. | Fallback Coverage |
| **G4** | State Machine Correctness & Query Latency | 100% of the transition table in `MEM-AD-2.0` §4 is covered by a passing unit test. `get_application()` and `list_applications()` execute in < 50ms against 10,000+ event histories on local SQLite. | Correctness + Performance |
| **G5** | Derived-View Rebuild Equivalence | `rebuild_derived_state()` output is byte-for-byte identical to the incrementally-derived state it replaces, across 5,000 randomized event histories. | Replay Parity |
| **G6** | SQLite Concurrency (WAL Mode) | 10 concurrent threads (5 readers, 5 writers) execute for 60 seconds without producing any `database locked` errors or data corruption in WAL mode with `busy_timeout=5000ms`. | Concurrency Safety |

---

## 5. Monitoring Gates (Non-Blocking)

| Gate | Target | Why Non-Blocking |
|---|---|---|
| **M1** | `get_application()` under 50ms (individual call) | A slow query at single-user scale is an inconvenience, not a correctness failure |
| **M2** | 30-day cooldown enforced for 100% of REJECTED transitions | Cooldown enforcement is validated by G1+G4; M2 tracks coverage gap trends |
| **M3** | Test coverage % across `src/` modules | Coverage percentage is a proxy signal, not a target to game — no hard threshold |
| **M4** | Lint/style cleanliness (`ruff`, `black`) | Cosmetic; does not affect correctness |

---

## 6. Acceptance Criteria Matrix

| Test Case | Gate(s) | Implementation Phase |
|---|---|---|
| Write then read a `MemoryEvent`, all fields intact including nested `payload` | G1 | Phase 1 |
| Process crash (SIGKILL) mid-write, event still retrievable on restart | G1 | Phase 2 |
| 1,000 duplicate `event_id` bursts → single row, derived state unchanged | G2 | Phase 2 |
| Malformed payload → `UNKNOWN` event type, no exception raised, full raw preserved | G3 | Phase 2 |
| Unknown future `event_type` string → `UNKNOWN` fallback, application status unchanged | G3 | Phase 2 |
| Every (from_status, event_type) transition cell has a passing test | G4 | Phase 2 |
| `list_applications()` on 10,000 event history returns in < 50ms | G4 | Phase 3 |
| 20-event incremental build vs. `rebuild_derived_state()` — byte-for-byte identical | G5 | Phase 3 |
| 5,000 randomized event histories rebuild with zero divergence | G5 | Phase 7 |
| 10-thread WAL concurrency stress (60 sec) — zero lock errors, zero corruption | G6 | Phase 7 |
| `check_domain_cooldown("x.com")` returns `is_blocked=True` within 30 days of REJECTED | G4 | Phase 4 |
| CLI `stale --days N` correct against hand-built test data | DoD `MEM-MP-2.0` §6 | Phase 5 |
| All 7 FastMCP tools callable by external MCP client | DoD `MEM-MP-2.0` §6 | Phase 6 |
| End-to-end application lifecycle via MCP client — full status correct | G4, G5 | Phase 7 |

---

## 7. Sign-Off Checklist

- [ ] Gates G1–G6 all pass in the automated `pytest` suite.
- [ ] Manual CLI dogfooding session completed and documented (commands run + outputs observed).
- [ ] `MEM-EC-2.0` Categories A–F each have at least one corresponding test.
- [ ] Sentiment Classifier `ClassifiedSignal` reconciliation task (`MEM-AD-2.0` §7) closed — proposed contract confirmed or corrected against actual v1.0.1 source.
- [ ] 30-day domain cooldown engine verified for 100% of `REJECTED` transitions.
- [ ] FastMCP tool schema validation passes for all 7 registered tools.
- [ ] `.gitignore` confirmed protecting SQLite files (verified via `git status` check).
