# Memory Module — Specification Suite Master Index

**CONDUCTOR / UNIFIED CAREEROS Subsystem #8 · Learning & State Layer**  
**Suite Version:** 2.0 · **Status:** Specification Complete — Approved for Unified CareerOS Integration  
**Date:** August 28, 2026  
**System Owner:** Soumyadeep Nath  
**Governance Anchor:** Law 8 (Memory Event Sourcing & Immutability — "Remember; Do Not Decide")

---

## 1. Purpose of This Index

This document is the master entry point and architectural compass for the **Memory Module Specification Suite**. In the Unified CareerOS ecosystem, Memory Module functions as the immutable, event-sourced ledger and centralized state materialized view across all 10 autonomous subsystems.

This index maps the six formal specifications so developers, AI sub-agents, and Conductor orchestrators can locate architectural decisions, schemas, state transition rules, and verification gates within seconds.

---

## 2. Document Suite Navigation

| # | Document | Document ID | Purpose & Key Question Answered |
|---|---|---|---|
| 1 | **[Problem Statement](file:///c:/My%20Projects/AI%20Native%20Job%20Agent%20Project/Memory%20Module/docs/Memory_Module_01_Problem_Statement_v1.0.md)** | `MEM-PS-2.0` | Why must CareerOS have an immutable event ledger, and what failures occur without it? |
| 2 | **[Mission Plan](file:///c:/My%20Projects/AI%20Native%20Job%20Agent%20Project/Memory%20Module/docs/Memory_Module_02_Mission_Plan_v1.0.md)** | `MEM-MP-2.0` | What are the exact mission objectives, governance laws, scope boundaries, and Definition of Done? |
| 3 | **[Architecture Design](file:///c:/My%20Projects/AI%20Native%20Job%20Agent%20Project/Memory%20Module/docs/Memory_Module_03_Architecture_Design_v1.0.md)** | `MEM-AD-2.0` | What is the data model, FastMCP tool mesh, state-machine logic, SQLite engine, and ADR rationale? |
| 4 | **[Implementation Plan](file:///c:/My%20Projects/AI%20Native%20Job%20Agent%20Project/Memory%20Module/docs/Memory_Module_04_Implementation_Plan_v1.0.md)** | `MEM-IP-2.0` | What is the phase-wise development roadmap, task breakdown, effort estimate, and exit gates? |
| 5 | **[Evaluation Plan](file:///c:/My%20Projects/AI%20Native%20Job%20Agent%20Project/Memory%20Module/docs/Memory_Module_05_Evaluation_Plan_v1.0.md)** | `MEM-EP-2.0` | How is correctness, idempotency, replay parity, and lock concurrency verified (Gates G1–G6)? |
| 6 | **[Edge Case Plan](file:///c:/My%20Projects/AI%20Native%20Job%20Agent%20Project/Memory%20Module/docs/Memory_Module_06_Edge_Case_Plan_v1.0.md)** | `MEM-EC-2.0` | What failure modes exist (Categories A–F) and what are their mitigation protocols? |

---

## 3. Position in the Unified CareerOS Ecosystem

```
+---------------------------------------------------------------------------------------------------+
|                                 UNIFIED CAREEROS TOPOLOGY & FLOW                                  |
|                                                                                                   |
|  [10] Candidate Profile JSON Engine (Master Truth Anchor) ─────────────────────────┐             |
|                                                                                    │              |
|  DISCOVERY & INTELLIGENCE                                                          │              |
|   [1] The Gleaner ──────► Emits: JOB_DISCOVERED                                  │              |
|   [4] Research Agent ─────► Emits: DOSSIER_COMPILED                                │              |
|   [5] Future-Fit ─────────► Emits: SKILL_GAP_EVALUATED                             │              |
|                                                                                    │              |
|  APPLICATION & OUTREACH                                                            │              |
|   [2] AlignResume ────────► Emits: RESUME_TAILORED                                 │ Read by      |
|   [3] Overture Outreach ──► Emits: OUTREACH_SENT                                   │              |
|   [7] PDF Auto-Apply ─────► Emits: APPLICATION_SUBMITTED                           │              |
|                                                                                    │              |
|  TRIAGE & SCHEDULING                                                               │              |
|   [9] Sentiment Classifier► Emits: RESPONSE_CLASSIFIED                             │              |
|   [6] MCP Chief of Staff ─► Emits: INTERVIEW_SCHEDULED                             │              |
|                                   │                                                │              |
|                                   ▼                                                │              |
|         +─────────────────────────────────────────────────────────────+            │              |
|         |                 [8] MEMORY MODULE (FastMCP)                 |◄───────────┘              |
|         |                                                             |                           |
|         |  • Immutable Append-Only Ledger (`memory_events`)           |                           |
|         |  • Materialized Derived Views (`application_records`)       |                           |
|         |  • Transition Audit Trail (`status_transitions`)            |                           |
|         |  • 30-Day Domain Cooldown Engine (`domain_cooldowns`)       |                           |
|         |  • Deterministic State Replay (`rebuild_derived_state`)     |                           |
|         |  • Zero LLM / Zero Embedding Cost in Core Path              |                           |
|         +──────────────────────────────┬──────────────────────────────+                           |
|                                        │ FastMCP Tools                                            |
|                                        ▼                                                          |
|  COORDINATION & EXECUTION                                                                         |
|   [0] Conductor Master DAG Coordinator (LangGraph Dynamic Engine)                                 |
|       Queries ground truth, enforces 30-day cooldowns, and routes next autonomous action           |
+---------------------------------------------------------------------------------------------------+
```

---

## 4. Cross-Component Integration Map

| Subsystem # | Component Name | Relationship to Memory Module | Event / Protocol Contract | Status |
|---|---|---|---|---|
| **[10]** | **Candidate Profile JSON** | Master Identity Anchor | Foreign Key `candidate_id` reference; opaque lookup | Spec Complete |
| **[1]** | **The Gleaner** | Upstream Producer | `JOB_DISCOVERED` (Job schema, source URL, company ID) | Spec Complete |
| **[2]** | **AlignResume** | Upstream Producer | `RESUME_TAILORED` (`TailoringRun` payload, diff summary) | Deployed v1.0 |
| **[3]** | **Overture Outreach** | Upstream Producer | `OUTREACH_SENT` (Recipient recruiter, channel, subject) | Built v1.0 |
| **[4]** | **Research Agent** | Upstream Producer | `DOSSIER_COMPILED` (Financial health, tech stack dossier) | Spec Complete |
| **[5]** | **Future-Fit** | Upstream Producer | `SKILL_GAP_EVALUATED` (Opportunity cost matrix, skill delta) | Deployed v1.0 |
| **[6]** | **MCP Chief of Staff** | Bi-Directional Peer | `INTERVIEW_SCHEDULED`, `CALENDAR_UPDATED`, triage queries | Spec Complete |
| **[7]** | **PDF Auto-Apply ("Usher")**| Upstream Producer | `APPLICATION_SUBMITTED` (ATS domain, fields, PDF artifact)| Spec Complete |
| **[8]** | **Memory Module** | **Core State Ledger** | FastMCP Server (`record_event`, `get_application`, etc.) | **This Suite** |
| **[9]** | **Sentiment Classifier** | Upstream Producer | `RESPONSE_CLASSIFIED` (`sentiment`, `urgency_score`) | Deployed v1.0.1 |
| **[0]** | **Conductor Orchestrator**| Primary Consumer | LangGraph State Graph querying Memory Module for DAG routing| Spec Complete |

---

## 5. Governance Constitution Alignment

Memory Module enforces **Law 8** of the CareerOS Governance Constitution:
1. **Append-Only Immutability:** Events once written to `memory_events` are never modified or deleted.
2. **Remember; Do Not Decide:** Memory Module computes derived *state* (what happened, what is true now), never derived *action* (what to do next).
3. **Deterministic Replayability:** Rebuilding the derived tables from `memory_events` produces 100% bit-for-bit identical state across any environment (`rebuild_derived_state()`).
4. **Universal Cooldown Enforcement:** Automatic tracking of 30-day domain cooldowns upon rejection events to prevent duplicate spam.
5. **Zero-Cost Critical Path:** Deterministic Python algorithms and SQLite storage without probabilistic LLM or embedding dependencies in the core storage path.

---

## 6. How to Navigate This Specification

- **Starting Implementation?** Begin with **`MEM-IP-2.0` (Implementation Plan)** and execute Phase 0 through Phase 5.
- **Implementing FastMCP Tools or Adapters?** Refer to **`MEM-AD-2.0` (Architecture Design)** §3 (Data Models), §5 (SQL Schema), and §7 (Integration Contracts).
- **Verifying System Correctness?** Execute the test harness according to **`MEM-EP-2.0` (Evaluation Plan)** covering Gates G1 through G6.
- **Handling Ambiguity or Failures?** Review **`MEM-EC-2.0` (Edge Case Plan)** for scenario classification and mitigation workflows.
