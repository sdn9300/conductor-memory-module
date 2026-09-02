# Memory Module — Edge Case Plan

**CONDUCTOR / UNIFIED CAREEROS Subsystem #8 · Learning & State Layer**  
**Document ID:** `MEM-EC-2.0` · **Version:** 2.0 · **Status:** Approved  
**Date:** August 28, 2026  
**System Owner:** Soumyadeep Nath  
**Governance Anchor:** Law 6 (No-Silent-Drop & Degrade), Law 8 (Memory Event Sourcing)  
**Related:** `MEM-AD-2.0`, `MEM-IP-2.0`, `MEM-EP-2.0`

---

## 1. Registry Structure & Severity Classification

Twenty-eight scenarios across six categories, ID-tagged as `EC-MEM-[CATEGORY]-[NUMBER]`.

Severity classifications:
- **Blocking** — Must be handled correctly before v2.0 ships. Maps to a hard-blocking Evaluation Gate.
- **Degraded** — System remains correct but a manual step or reduced functionality results. Requires documenting and logging; may trigger `MANUAL_NOTE`.
- **Cosmetic** — Worth cataloguing; not worth engineering around at current scale.

---

## 2. Category A — Data Integrity & Out-of-Order Delivery

| ID | Scenario | Expected Handling | Severity |
|---|---|---|---|
| **EC-MEM-A01** | Same event delivered twice (producer retry after a network timeout) | Deduplicated by deterministic `event_id` hash (ADR-5). Second `record_event()` call is a confirmed no-op — zero duplicate rows, derived state unchanged | **Blocking** |
| **EC-MEM-A02** | Events arrive out of order — e.g. `RESPONSE_CLASSIFIED` ingested before `APPLICATION_SUBMITTED` due to async race between producers | Both events logged in `memory_events` with their true `occurred_at` timestamps. State machine applies them in `occurred_at` order during `rebuild_derived_state()`, not arrival order. Final derived state is always correct regardless of delivery sequence | **Blocking** |
| **EC-MEM-A03** | Payload missing a required field due to an upstream bug | Captured as `event_type = UNKNOWN`, full raw `payload_json` preserved, ingestion does not raise. Status of the linked `ApplicationRecord` is unchanged | **Blocking** |
| **EC-MEM-A04** | Two conflicting signals arrive for the same application in close succession (e.g., `interview_invite` followed immediately by `rejection`) | Both events retained in `memory_events`. Derived status uses most-recent-by-`occurred_at`. Conflict is never silently resolved — `get_history()` always exposes both, enabling human review | **Degraded** |
| **EC-MEM-A05** | Producer clock drift causes `occurred_at` to arrive before the previous event's timestamp by more than 60 seconds | Event ingested with its reported `occurred_at` unchanged. If this causes out-of-order state on full rebuild, `rebuild_derived_state()` re-orders by `occurred_at ASC` and recovers correct state. Clock drift is logged as a warning | **Degraded** |

**Recovery Protocol for A02 / A05:** On ingestion, if `occurred_at` is earlier than the most recent event for the same `application_id`, the full event stream is flagged for re-ordering. `rebuild_derived_state()` should be triggered after bulk ingestion sessions to guarantee derived view correctness.

---

## 3. Category B — Schema Evolution & Unknown Event Types

| ID | Scenario | Expected Handling | Severity |
|---|---|---|---|
| **EC-MEM-B01** | A new `event_type` string arrives from a component not yet integrated (e.g., a future Research Agent version ships before its adapter is written) | Falls into the `UNKNOWN` bucket. Full raw payload preserved in `payload_json`. Ingestion does not crash. `ApplicationRecord.status` is unchanged | **Blocking** |
| **EC-MEM-B02** | An existing producer changes its payload shape without notice (e.g., future Sentiment Classifier version renames `urgency_score` to `urgency_level`) | Pydantic validation at the ingestion boundary catches the mismatch for structured parsing. Raw payload is still written to `payload_json` regardless — zero data loss even when structured interpretation fails | **Blocking** |
| **EC-MEM-B03** | Candidate Profile JSON [10] schema is finalized after Memory Module deployment with different field conventions | No impact. Memory Module only references `candidate_id` as an opaque foreign key — never reads or writes Candidate Profile internal fields (ADR boundary discipline) | **Cosmetic** |
| **EC-MEM-B04** | Memory Module itself is upgraded with new `EventType` enum values while old events remain in `memory_events` | Old events with now-valid type strings parse correctly. Old events with deprecated types remain as `UNKNOWN` with raw payload preserved. `rebuild_derived_state()` handles both safely | **Degraded** |

---

## 4. Category C — State Machine Ambiguity & Soft-Terminal Handling

| ID | Scenario | Expected Handling | Severity |
|---|---|---|---|
| **EC-MEM-C01** | Sentiment Classifier's `urgency_score` / `recommended_action` reflects the EC-AMBIG-010 miscalibration pattern (deadline language in a rejection email inflating urgency score) | Memory Module treats `urgency_score` and `recommended_action` as *advisory metadata only*. Automatic terminal-state transitions are never triggered solely by urgency threshold. Raw `ClassifiedSignal` is always retained in `payload_json` so a future Sentiment Classifier recalibration can be re-applied by replaying history via `rebuild_derived_state()` | **Blocking** |
| **EC-MEM-C02** | A rejection signal arrives after `INTERVIEW_SCHEDULED` | Valid transition per `MEM-AD-2.0` §4 — post-interview rejection is a legitimate lifecycle event, not an error | **Cosmetic** (by design) |
| **EC-MEM-C03** | A recruiter reverses an earlier rejection (positive follow-up signal arrives after `REJECTED` status) | `REJECTED` is a soft-terminal state — reversible via an explicit `MANUAL_NOTE` event with a status override field. Never auto-reversed by an incoming `RESPONSE_CLASSIFIED` event (prevents miscalibrated classifiers from flipping statuses autonomously) | **Degraded** |
| **EC-MEM-C04** | No signal ever arrives — the application goes silent indefinitely | `GHOSTED` is not event-driven. It is computed at query time from elapsed days since `last_updated` via `get_stale_applications(days_silent)`. This deliberately breaks the "everything is event-triggered" pattern — the only exception — flagged here precisely because it is easy to accidentally implement as a missing state-machine transition | **Blocking** |
| **EC-MEM-C05** | `AMBIGUOUS_OUTCOME` status is derived from an ambiguous `RESPONSE_CLASSIFIED` signal (e.g., classifier confidence < 0.6) | Event logged, status set to `AMBIGUOUS_OUTCOME`, flagged for manual review via CLI or `MANUAL_NOTE` override. System does not guess at the true outcome | **Degraded** |

---

## 5. Category D — Multi-Application Disambiguation

| ID | Scenario | Expected Handling | Severity |
|---|---|---|---|
| **EC-MEM-D01** | Candidate applies to multiple concurrent roles at the same company | `application_id` is scoped per (company, role, discovery event), never per company alone. A recruiter reply must be matched by an explicit `application_id` supplied by the producing component, not inferred from company name | **Blocking** |
| **EC-MEM-D02** | Candidate re-applies to a company that previously rejected them within the 30-day cooldown window | `check_domain_cooldown(domain)` returns `is_blocked=True`. The Gleaner and PDF Auto-Apply must check this before queueing or submitting. Memory Module blocks duplicate records but does not autonomously prevent the application — it is the responsibility of producing agents to query cooldown status | **Blocking** |
| **EC-MEM-D03** | Candidate re-applies to a company after the 30-day cooldown expires | A new `application_id` is created. The old record and rejection event are never deleted — full historical relationship with the employer remains visible in `get_history()`, including prior rejection date | **Degraded** |
| **EC-MEM-D04** | A recruiter reply cannot be confidently matched to any existing `application_id` (e.g., no thread reference in email headers) | Logged as an orphaned interaction in `memory_events` with `application_id = null`. Flagged for manual linking via `MANUAL_NOTE`. Never force-matched to a guessed application | **Degraded** |

---

## 6. Category E — Operational & Infrastructure

| ID | Scenario | Expected Handling | Severity |
|---|---|---|---|
| **EC-MEM-E01** | Concurrent writers (Conductor DAG and CLI session writing simultaneously) | SQLite WAL mode allows concurrent readers + one writer. Second writer blocks and retries with `busy_timeout=5000ms` rather than corrupting data. If retries exceed timeout, operation fails with a clear error (not a silent data loss). Explicit trigger for PostgreSQL migration evaluation | **Degraded** |
| **EC-MEM-E02** | Disk full or write interrupted mid-transaction | All writes wrapped in explicit SQLite transactions with `BEGIN IMMEDIATE`. A failed write cannot leave a partially-written row — SQLite transaction atomicity guarantees clean rollback | **Blocking** |
| **EC-MEM-E03** | Database file accidentally deleted or corrupted | No automated backup in v2.0 (out of scope). Documented mitigation: periodic manual export to versioned JSON dump via `rebuild_derived_state()` + export script. SQLite's single-file nature makes ad-hoc backup trivial | **Cosmetic** |
| **EC-MEM-E04** | FastMCP server process crashes mid-tool-call | Client receives an MCP error response (not a silent hang). `memory_events` write that was in-flight is either committed or rolled back cleanly (transaction atomicity). No partial state corruption | **Degraded** |
| **EC-MEM-E05** | Very large `payload_json` blob (e.g., full resume PDF binary accidentally embedded) | Write proceeds but `payload_json` exceeds recommended excerpt-only convention. Log warning. Implement a `max_payload_bytes` soft guard in the ingestion adapter (not in `MemoryStore` core) | **Degraded** |

---

## 7. Category F — Privacy & Security

| ID | Scenario | Expected Handling | Severity |
|---|---|---|---|
| **EC-MEM-F01** | The SQLite database file (containing recruiter names, email fragments, company outcomes) is committed to the public GitHub repository | Prevented structurally: `.gitignore` entry added in Phase 0, before the first commit. Same repo-hygiene discipline applied proactively here that was previously applied reactively to AlignResume's stray `.agents/` directory | **Blocking** |
| **EC-MEM-F02** | `MemoryEvent.payload` stores a full verbatim recruiter email body | Recommended practice (enforced at adapter boundary, not by `MemoryStore` core): producers pass a reference ID and short excerpt, not the full email body, to limit exposure if the SQLite file is accidentally shared | **Degraded** |
| **EC-MEM-F03** | A producer accidentally includes an API key or auth token inside an event payload (e.g., leftover debug data from Overture) | Not detectable or preventable by Memory Module directly. Documented here as an explicit contract expectation on all producing sub-agents. Consistent with `MEM-AD-2.0` §7 integration contracts | **Cosmetic** |
| **EC-MEM-F04** | `domain_cooldowns` table reveals a candidate's rejection history to a third-party code reviewer | SQLite file is `.gitignore`'d (F01 control). CLI and FastMCP queries require local authenticated access — no remote exposure in v2.0 | **Cosmetic** |

---

## 8. Coverage Cross-Reference

Every **Blocking** scenario maps to at least one Hard-Blocking Evaluation Gate:

| Blocking Scenarios | Evaluation Gate |
|---|---|
| EC-MEM-A01, A02, A03 | G1 (Durability), G2 (Idempotency), G3 (Fallback) |
| EC-MEM-B01, B02 | G3 (Fallback Coverage) |
| EC-MEM-C01, C04 | G4 (State Machine Correctness) |
| EC-MEM-D01, D02 | G4 (Cooldown Enforcement) |
| EC-MEM-E02 | G1 (Transaction Atomicity) |
| EC-MEM-F01 | Structural prevention in Phase 0 (not an automated gate — see `MEM-IP-2.0` §3) |

**No Blocking-severity scenario in this registry is left without either an automated gate, a structural prevention, or a named Phase deliverable.** If a future revision adds a Blocking scenario here without a corresponding control, that is the explicit signal the Evaluation Plan (`MEM-EP-2.0`) needs updating before the next release cycle.
