# Project Scope Document

## Project Name: BDIPlus Agent Evaluation & Release Gating Hub (`BDIPlus-AgentEval-Hub`)

* **Document Version:** 1.0.0  
* **Author:** Digvijay Jere  
* **Target Platform:** Google Antigravity / Enterprise Data Transformation Consulting  
* **Associated Documents:** [BRD.md](file:///c:/Users/Admin/OneDrive/Desktop/Agent_evaluation/BRD.md) | [FRD.md](file:///c:/Users/Admin/OneDrive/Desktop/Agent_evaluation/FRD.md)  
* **Date:** 2026-11-02  

---

## 1. Project Background & Objective

BDIPlus develops and deploys enterprise AI agents tailored for Customer Data Platforms (CDP) and financial/insurance domain workflows. Prior to this initiative, agent verification relied on manual, subjective spot-checking taking up to 3 days per release cycle. This manual approach created deployment bottlenecks, failed to capture regression across prompt iterations, and provided no automated gating mechanism to block substandard builds.

The **BDIPlus-AgentEval-Hub** establishes an automated, reproducible testing and release gating framework. This document formally defines the boundaries, deliverables, out-of-scope items, work breakdown structure (WBS), resource responsibilities, and acceptance criteria for the project.

---

## 2. In-Scope Deliverables & Features

The project encompasses the design, implementation, and verification of five core functional pillars:

```
+----------------------------------------------------------------------------------------------------+
|                                    IN-SCOPE SYSTEM BOUNDARIES                                      |
+----------------------------------------------------------------------------------------------------+
|  1. Dataset Harness           2. Evaluation Engine           3. Scoring Architecture               |
|  - Pydantic Schema Models     - Pytest Runner Architecture   - Deterministic (P, R, F1, EM)        |
|  - Multi-Segment Data Curation - Parallel Test Runner        - LLM-as-a-Judge (1-5 Rubrics)        |
|  - Adversarial Test Vectors   - Timeout & Execution Controls - Faithfulness / Hallucination        |
+-------------------------------+------------------------------+-------------------------------------+
|  4. Release Gating Engine     5. Observability & Sinks       6. CI/CD Tooling & Reports            |
|  - Baseline vs Candidate      - Langfuse SDK Ingestion       - Pytest CLI Flags (`--gate`)         |
|  - Math Regression Thresholds - Trace / Span Hierarchies     - Exit Code Gates (0 vs 1)            |
|  - Configurable Delta Bounds  - Audit Metadata Capture       - Markdown / JSON Summary Artifacts   |
+-------------------------------+------------------------------+-------------------------------------+
```

### 2.1 Test Data Management & Multi-Segment Datasets
* **Structured Dataset Schema:** Standardized JSON/JSONL dataset formats backed by Pydantic models with field-level validations.
* **Segmented Golden Benchmark Suites:**
  * **Normal / Expected:** High-confidence baseline queries for retail banking (balances, transactions, fund transfers) and insurance policies (deductibles, coverage limits, claim submission).
  * **Degraded / Corrupted:** Missing customer attributes, corrupted JSON payloads, truncated query strings, and incomplete CDP records.
  * **Customer Segment Variations:** Specialized domain terminology comparing retail banking compliance versus commercial insurance underwriting policies.
  * **Adversarial & Vulnerability Vectors:** Prompt injection payloads, system prompt extraction attempts, jailbreaks, and cross-tenant data leak probes.
* **Dataset Immutability:** SHA-256 integrity validation for golden test suites to prevent unversioned drifts.

### 2.2 Pytest-Based Evaluation Test Harness
* **Native Pytest Integration:** Custom `pytest` plugin hooks, fixtures, and configuration decorators.
* **Endpoint Connectors:** Configurable client adapters supporting REST API HTTP endpoints, local Python callable agents, and mock fixtures.
* **Concurrent Execution:** Parallel execution utilizing `pytest-xdist` to accelerate end-to-end evaluation runs.
* **Execution Guardrails:** Configurable request timeouts, retry handlers for transient errors, and structured execution logging.

### 2.3 Dual-Tier Scoring & Evaluation Engine
* **Deterministic Metric Calculators:**
  * Exact Match (EM) for strict classification and entity retrieval.
  * Precision, Recall, and F1 calculation for multi-entity extraction tasks.
  * Output schema compliance verification (JSON/Pydantic validation).
  * Latency tracking ($p_{50}, p_{95}, p_{99}$).
* **LLM-as-a-Judge Grader Module:**
  * Zero-temperature deterministic prompt templates with strict JSON response enforcement.
  * 1–5 Likert evaluation scales with explicit scoring rubrics for:
    * **Faithfulness & Groundedness** (anti-hallucination verification against context documents).
    * **Answer Relevance & Completeness** (coverage of core customer query requirements).
    * **Constraint & Regulatory Adherence** (disclaimer presence, refusal of prohibited advice).

### 2.4 Automated Regression Detection & Release Gating
* **Baseline Comparator:** Automated ingestion of reference baseline metrics and side-by-side delta calculation against the candidate agent.
* **Mathematical Regression Detection:** Calculation of percentage degradation ($\Delta M$) and absolute point drops ($\delta M$).
* **Automated Release Gating:**
  * CLI `--gate` flag to abort build pipelines (exit code `1`) upon threshold violation (default: $>3\%$ drop in F1 or precision, or any P0 adversarial test failure).
  * Generation of human-readable Markdown release gate reports and machine-readable JSON artifacts.

### 2.5 Enterprise Observability & Langfuse Sink
* **Trace & Span Logging:** Automatic instrumentation sending evaluation runs, suites, and test cases as hierarchical traces into Langfuse.
* **Metric & Score Sinks:** Discrete numeric score publishing (`metric:faithfulness`, `metric:f1_score`, etc.) tagged with evaluation run metadata, commit SHAs, and model tags.
* **Compliance Audit Trail:** Direct URL generation linking CI/CD runs to Langfuse traces for audit compliance.

---

## 3. Out-of-Scope Items (Exclusions & Boundaries)

To ensure laser focus on evaluation and release gating, the following areas are strictly **Out-of-Scope**:

| Item | Description | Rationale |
| :--- | :--- | :--- |
| **Model Pre-training & Fine-tuning** | Training, LoRA fine-tuning, or parameter updates for foundational LLMs. | The hub evaluates model outputs black-box / gray-box; model training is managed by upstream ML platform teams. |
| **Custom Graphical User Interface (GUI)** | Developing dedicated React/Vue web applications or front-end portals. | The framework focuses on CLI, automated CI/CD runners, and headless evaluation. Langfuse provides the visual dashboard. |
| **Production Inference Hosting** | Orchestrating production agent deployment, autoscaling, or Kubernetes serving pods. | Handled by BDIPlus production platform DevOps infrastructure. |
| **Real Customer PII / Live Data Ingestion** | Extracting or ingesting unmasked live customer data from production CDPs. | Evaluation must strictly use synthetic, de-identified, or approved golden benchmarks to maintain regulatory compliance. |
| **Non-Agent Infrastructure Monitoring** | Server metrics, CPU/memory profiling, database monitoring, or cluster health checks. | Handled by standard infrastructure monitoring tools (e.g., Datadog, Prometheus). |
| **Human-in-the-Loop Review UI** | Interactive browser interfaces for manual human annotation or labelling. | Focus is strictly on automated deterministic rules and LLM-as-a-judge scoring. |

---

## 4. Work Breakdown Structure (WBS) & Milestones

The project will be delivered in four sequential, milestone-driven phases:

```
+----------------------------------------------------------------------------------------------+
| Phase 1: Test Data & Schema Architecture                                   Target: Days 1-5  |
| - Standardize Pydantic test case schemas                                                     |
| - Curate multi-segment synthetic golden datasets (banking, insurance, adversarial)           |
| - Implement dataset loader and SHA-256 integrity checkers                                    |
+--------------------------------------------------------------+-------------------------------+
                                                               |
                                                               v
+----------------------------------------------------------------------------------------------+
| Phase 2: Scoring Engines & Pytest Harness                                 Target: Days 6-12  |
| - Build deterministic metric library (Precision, Recall, F1, EM)                             |
| - Construct LLM-as-a-judge grading prompts with temperature=0 and JSON output parsing        |
| - Implement core pytest fixtures, CLI parameters, and parallel execution harness             |
+--------------------------------------------------------------+-------------------------------+
                                                               |
                                                               v
+----------------------------------------------------------------------------------------------+
| Phase 3: Regression Detection & Release Gating Engine                     Target: Days 13-17 |
| - Implement baseline vs candidate metric delta engine                                        |
| - Implement `--gate` threshold enforcement logic and exit code gates                         |
| - Generate automated Markdown and JSON release summary reports                               |
+--------------------------------------------------------------+-------------------------------+
                                                               |
                                                               v
+----------------------------------------------------------------------------------------------+
| Phase 4: Langfuse Observability & CI/CD Pipeline Hooks                    Target: Days 18-22 |
| - Implement Langfuse SDK trace and metric sink integration                                   |
| - Build CI/CD workflow action templates (GitHub Actions / GitLab CI)                         |
| - Conduct full end-to-end dry runs and validation against sample CDP agents                   |
+----------------------------------------------------------------------------------------------+
```

---

## 5. Stakeholder Roles & RACI Matrix

* **R (Responsible):** The role that performs the activity.  
* **A (Accountable):** The role with final approval and ownership.  
* **C (Consulted):** Role offering domain input and advisory feedback.  
* **I (Informed):** Role kept updated on progress and results.

| Project Activity / Deliverable | Agent Eval Engineers | Lead Engineers / Release Mgrs | Domain Stakeholders (Fin/Ins) | DevOps / Platform Engineers |
| :--- | :---: | :---: | :---: | :---: |
| Dataset Schema & Curation | **R** | **A** | **C** | **I** |
| Evaluation Harness & Pytest Plugin | **R** | **A** | **I** | **C** |
| LLM Judge Rubrics & Prompts | **R** | **C** | **A** | **I** |
| Release Gating & Threshold Rules | **C** | **A** | **C** | **I** |
| Langfuse Telemetry Integration | **R** | **C** | **I** | **A** |
| CI/CD Pipeline Automation | **C** | **A** | **I** | **R** |
| Release Authorization Sign-off | **I** | **A** | **C** | **I** |

---

## 6. Assumptions, Dependencies & Constraints

### 6.1 Technical Assumptions
1. Target AI agents expose an HTTP REST endpoint or a standard Python callable interface accepting JSON inputs and returning text/JSON responses.
2. An enterprise LLM API (e.g., Gemini 1.5 Pro / GPT-4o) is provisioned with sufficient rate limits (minimum 60 requests/minute) to serve as the evaluation judge.
3. Langfuse instance (Cloud or self-hosted) is provisioned with project API keys accessible to the execution environment.

### 6.2 Constraints
1. **Runtime Environment:** Python 3.11+ running in standard containerized CI/CD runners.
2. **Determinism:** LLM-as-a-judge prompts must strictly run with `temperature = 0.0`.
3. **Execution Time:** Full suite run on a standard 200-sample dataset must finish within 8 minutes under parallel execution.
4. **Data Privacy:** Datasets must use synthetic mock customer records with zero real-world PII.

---

## 7. Risk Management & Mitigation Matrix

| Risk ID | Identified Risk | Impact | Probability | Mitigation Strategy |
| :--- | :--- | :---: | :---: | :--- |
| **RSK-01** | LLM judge rate-limiting (HTTP 429) slows CI/CD runs | High | Medium | Implement exponential backoff, batch request chunking, and worker concurrency throttling. |
| **RSK-02** | LLM judge scoring variance across runs | High | Low | Enforce `temperature=0`, fixed random seed, strict few-shot examples, and discrete JSON schema extraction. |
| **RSK-03** | Test dataset leakage or unversioned edits | Medium | Low | Store test datasets in Git with SHA-256 integrity verification during test pre-flight. |
| **RSK-04** | Langfuse endpoint unreachable during gate check | Medium | Low | Non-blocking telemetry sink option: log locally and queue traces asynchronously without failing the build gate. |
| **RSK-05** | False positive gate failures due to minor metric noise | High | Medium | Configure relative threshold tolerances ($\ge 3\%$) and establish secondary review escalation paths. |

---

## 8. Acceptance & Sign-off Criteria

The project deliverables will be formally accepted upon fulfilling the following verification criteria:

1. **Test Dataset Completeness:** At least 200 validated test cases covering all four segments (expected, degraded, domain-specific, adversarial) conforming to the Pydantic schema.
2. **Dual-Tier Scoring Operational:**
   * Deterministic calculations (Precision, Recall, F1, EM) validated against known mathematical test fixtures.
   * LLM-as-a-judge successfully scoring on a 1–5 scale with structured JSON outputs and $\ge 98\%$ score stability across identical runs.
3. **Automated Gating Verification:**
   * Simulated candidate regression ($>3\%$ metric drop) consistently triggers exit code `1` and generates a failure report.
   * Compliant candidate runs trigger exit code `0` and approve release.
4. **Langfuse Integration Complete:** Telemetry spans, prompt traces, and evaluation scores appear in the Langfuse dashboard with valid metadata linkage.
5. **Documentation Delivery:** Delivery and approval of [BRD.md](file:///c:/Users/Admin/OneDrive/Desktop/Agent_evaluation/BRD.md), [FRD.md](file:///c:/Users/Admin/OneDrive/Desktop/Agent_evaluation/FRD.md), and [SCOPE.md](file:///c:/Users/Admin/OneDrive/Desktop/Agent_evaluation/SCOPE.md).
