# Memory Module — Problem Statement & Failure Surface Analysis

**CONDUCTOR / UNIFIED CAREEROS Subsystem #8 · Learning & State Layer**  
**Document ID:** `MEM-PS-2.0` · **Version:** 2.0 · **Status:** Approved for Implementation  
**Date:** August 28, 2026  
**System Owner:** Soumyadeep Nath  
**Governance Anchor:** Law 8 (Memory Event Sourcing & Immutability — "Remember; Do Not Decide")  
**Related Documents:** `MEM-MP-2.0` (Mission Plan), `MEM-AD-2.0` (Architecture Design), `CAREEROS-PS-v2.1`

---

## 1. Executive Context

The **Unified AI-Native Career Operating System (CareerOS)** is a 10-subsystem autonomous pipeline designed to discover, tailor, apply, and negotiate technical careers. As of August 2026, the ecosystem state is distributed across active sub-agents:

| Subsystem # | Component Name | Architectural Role | Current Status |
|---|---|---|---|
| **[10]** | **Candidate Profile JSON** | Master Identity & Truth Anchor | Spec Complete |
| **[1]** | **The Harvester (Gleaner)** | Multi-Source Job Discovery & Ingestion | Spec Complete |
| **[2]** | **AlignResume** | Truthfulness-Guarded Resume Tailoring | Deployed v1.0 |
| **[3]** | **Overture Outreach** | Recruiter Outreach & Follow-up | Built v1.0 |
| **[4]** | **Research Agent** | Pre-Application Company Intelligence | Spec Complete |
| **[5]** | **Future-Fit** | Predictive Skill Gap & Opportunity Cost | Deployed v1.0 |
| **[6]** | **MCP Chief of Staff** | Autonomous Calendar & Triage Hub | Spec Complete |
| **[7]** | **PDF Auto-Apply ("Usher")** | ATS Final-Mile Form Submission (DRAFT mode)| Spec Complete |
| **[8]** | **Memory Module** | **Event-Sourced Append-Only State Ledger** | **This Build** |
| **[9]** | **Sentiment Classifier** | Recruiter Email Triage & Urgency Scoring | Deployed v1.0.1 |
| **[0]** | **Conductor Orchestrator** | Master LangGraph DAG Dynamic Coordinator | Spec Complete |

The successful deployment of **Sentiment Classifier (v1.0.1)** and **AlignResume (v1.0)** creates an urgent architectural bottleneck: high-signal lifecycle events (tailored resumes, outreach messages, recruiter sentiment classifications, interview invitations, ATS submission receipts) are generated, but without a centralized, persistent, event-sourced memory ledger, these signals are isolated in local process memory or private SQLite tables.

---

## 2. The Core Problem: Multi-Agent Amnesia & Distributed Incoherence

Without a dedicated, immutable, event-sourced memory subsystem, the multi-agent CareerOS ecosystem suffers from five catastrophic failure modes:

```
+---------------------------------------------------------------------------------------------------+
|                                  THE DISTRIBUTED AMNESIA PROBLEM                                  |
|                                                                                                   |
|  [The Harvester] ──► Discovers Job X                                                              |
|  [AlignResume]   ──► Generates Tailored Resume for Job X                                          |
|  [Overture]      ──► Sends Outreach for Job X                                                     |
|  [PDF Auto-Apply]──► Submits Application on Greenhouse ATS for Job X                              |
|  [Sentiment]     ──► Classifies Email: "Not moving forward with candidate"                        |
|                                                                                                   |
|                                     ✖ NO CENTRAL LEDGER ✖                                         |
|                                                                                                   |
|  1. PDF Auto-Apply re-applies to Job X tomorrow (Violates company 30-day cooldown).               |
|  2. Conductor DAG cannot decide next step because state must be re-inferred from raw emails.      |
|  3. Recruiter sentiment signals are discarded after classification (Signal loss).                |
|  4. Candidate has no unified audit trail during interviews to know what resume version was sent.   |
|  5. System state cannot be replayed or debugged after an agent crash.                             |
+---------------------------------------------------------------------------------------------------+
```

### 2.1 Concrete Failure Modes

1. **Orchestration Paralysis in Conductor [0]:**  
   Conductor must determine dynamic routing: *Has this role been applied to? Is an ATS submission pending human approval? How many days of silence warrant a follow-up email?* Without an authoritative state store, Conductor would be forced to query every sub-agent's private logs or parse email inboxes ad hoc, violating separation of concerns and introducing race conditions.

2. **Duplicate Application & Recruiter Spam (Violating 30-Day Cooldowns):**  
   If an ATS application is rejected or an outreach email is sent, sub-agents operating without shared memory will re-discover the same role and attempt repeated applications, triggering spam filters and destroying candidate professional credibility.

3. **Silent Signal Loss from Sentiment Classifier [9]:**  
   Sentiment Classifier parses recruiter emails and extracts high-signal outcomes (`interview_invite`, `rejection`, `info_request`, `urgency_score`). Without Memory Module, these classified signals evaporate after execution, leaving no persistent record of recruiter feedback.

4. **Lack of Truthful Auditability for Candidate Interview Prep:**  
   During live recruiter screening and technical interviews, the candidate needs instant, reliable recall: *Which exact resume bullets were sent? What outreach copy was used? What was the recruiter's exact wording on August 15th?* A fragmented system forces the candidate to reconstruct history manually under interview pressure.

5. **State Corruption from Non-Deterministic Models:**  
   If application state is stored as a single mutable row updated by LLMs, hallucinated model outputs or network retries can permanently overwrite historical truth.

---

## 3. The Solution: Event Sourcing & Law 8 ("Remember; Do Not Decide")

Memory Module solves these failures by implementing an **Event-Sourced Hybrid Ledger** backed by SQLite (WAL mode) and FastMCP:

1. **`memory_events` Table (Append-Only Ground Truth):** Every action across the 10 subsystems is recorded as an immutable, hash-deduplicated event. Events are never modified or deleted.
2. **`application_records` & `status_transitions` (Derived Materialized Views):** Current application status is deterministically derived by executing a pure, 100% unit-tested state machine over the event stream.
3. **Deterministic Replay (`rebuild_derived_state()`):** If a state-machine bug is patched or new metrics are added, the entire historical state can be rebuilt from scratch with 100% byte-for-byte consistency.
4. **FastMCP Tool Mesh:** Sibling sub-agents interact with Memory Module exclusively via typed Model Context Protocol tool endpoints (`record_event`, `get_application`, `get_history`, `check_domain_cooldown`).
5. **Zero LLM in the Storage Critical Path:** Ingestion, deduplication, state transitions, and queries use 100% deterministic Python and SQL (zero token costs, zero latency degradation, zero hallucinations).

---

## 4. Architectural Non-Goals for v1.0 / v2.0

To maintain rigorous scope discipline and guarantee sub-millisecond execution, the following are explicitly out of scope for the core Memory Module build:

| Non-Goal | Architectural Rationale | Deferred To |
|---|---|---|
| **Probabilistic / Vector RAG Memory** | Exact application tracking requires structured SQL queries (`WHERE status='applied'`), not fuzzy semantic search. | DevOps Phase 14 / Agentic AI Stage 03 Qdrant Capstone |
| **Model-Driven Action Routing** | Memory Module only remembers state; it never decides next actions. Action routing belongs strictly to Conductor. | Conductor Orchestrator [0] |
| **Candidate Identity & Resume Fact Storage** | Candidate Profile JSON [10] is the sole master anchor for candidate facts. Memory Module stores foreign keys (`candidate_id`), not identity data. | Candidate Profile JSON [10] |
| **Direct Browser or ATS Execution** | Memory Module logs application events; it does not scrape or automate ATS submissions. | PDF Auto-Apply Agent [7] |
| **Graphical Dashboard / Web UI** | Memory Module exposes FastMCP tools and a rich CLI harness; a full web dashboard is maintained at the ecosystem level. | CareerOS Unified Web UI |

---

## 5. Stakeholder Impact Matrix

| Stakeholder / Agent | Positive Impact with Memory Module | Risk if Memory Module is Absent |
|---|---|---|
| **Conductor Master DAG [0]** | Queries instantaneous ground-truth state via FastMCP to route next actions deterministically. | Operates blind; forced to scrape disparate logs or parse emails ad hoc. |
| **The Harvester [1]** | Checks `check_domain_cooldown()` before queueing discovered jobs, eliminating duplicates. | Queues duplicate jobs, wasting tailoring tokens and candidate time. |
| **PDF Auto-Apply [7]** | Logs submission receipts and verifies prior application state before launching browser. | Violates ATS rate limits and submits duplicate applications. |
| **Sentiment Classifier [9]** | Writes classified recruiter sentiment directly to the ledger with full raw payload audit. | High-value classified signals are discarded upon generation. |
| **Soumyadeep Nath (Candidate)** | Instant CLI query for interview prep: exact timeline, recruiter replies, and tailored resume diffs. | Manually cross-references inboxes and spreadsheets with risk of error. |

---

## 6. High-Level Success Criteria

The Memory Module specification is satisfied when:
1. **Zero Data Loss:** 100% of events emitted by upstream producers are durably written to SQLite.
2. **Deterministic Idempotency:** Duplicate events (same hash ID) result in zero duplicate rows or corrupted state.
3. **Full Replay Equivalence:** `rebuild_derived_state()` replays `memory_events` to produce byte-for-byte identical state with incrementally derived records (Evaluation Gate G5).
4. **Sub-50ms Query Latency:** Local SQLite queries execute under 50ms across 10,000+ event histories.
5. **Universal Cooldown Safety:** 30-day domain rejection cooldowns are strictly enforced across all application pipelines.
