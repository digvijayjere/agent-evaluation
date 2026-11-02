# Enterprise AI Agent Evaluation & Release Gating Hub

An enterprise evaluation framework, deterministic & LLM-as-a-judge scoring engine, and automated release gating pipeline for Customer Data Platform (CDP) AI agents in Retail Banking and Insurance domains.

---

## Architecture Overview

```
                                +-----------------------------+
                                |  150 Golden Benchmark Cases |
                                |   (SHA-256 Checksum Bound)  |
                                +--------------+--------------+
                                               |
                                               v
+-------------------+             +---------------------------+
|  Candidate Agent  | <---------> |  Pytest Evaluation Engine |
| (REST / In-Memory)|             | (tests/eval/test_agent...) |
+-------------------+             +-------------+-------------+
                                                |
                       +------------------------+------------------------+
                       |                                                 |
                       v                                                 v
         +----------------------------+                    +----------------------------+
         |    Deterministic Engine    |                    |     LLM-as-a-Judge Engine  |
         | (Exact Match, Precision,   |                    | (Faithfulness, Relevance,  |
         |  Recall, F1, Latency p95)  |                    |  P0 Constraint Adherence)  |
         +-------------+--------------+                    +-------------+--------------+
                       |                                                 |
                       +------------------------+------------------------+
                                                |
                                                v
                               +---------------------------------+
                               | Regression & Release Gate Engine|
                               | (Relative drop <= 3%, Exit 0/1) |
                               +----------------+----------------+
                                                |
                       +------------------------+------------------------+
                       |                                                 |
                       v                                                 v
         +----------------------------+                    +----------------------------+
         |     Reports & Dashboards   |                    |    Enterprise Observability|
         | (RELEASE_GATE.md, JSON)    |                    |  (Langfuse Traces & Spans) |
         +----------------------------+                    +----------------------------+
```

---

## 1. Quickstart & Verification

Ensure dependencies are installed:
```bash
pip install -r requirements.txt
```

### Run All Tests (77 passing tests)
```bash
pytest tests/unit tests/eval/test_e2e_pipeline.py -v
```

---

## 2. How to Check Each Milestone

| Milestone | Terminal Command | What It Checks |
| :--- | :--- | :--- |
| **Phase 1: Golden Datasets** | `pytest tests/unit/test_phase1_datasets.py -v` | Validates 150 test cases across 4 datasets, Pydantic schemas, and SHA-256 integrity. |
| **Phase 2: Dual Scoring** | `pytest tests/unit/test_phase2_scoring.py -v` | Validates Exact Match, F1, Precision, Recall, and LLM Judge rubrics & parsing. |
| **Phase 3: Release Gating** | `pytest tests/unit/test_phase3_gating.py -v` | Validates mathematical deltas, 3% regression tolerance, exit codes 0 vs 1. |
| **Phase 4: Full E2E & Telemetry**| `pytest tests/eval/test_e2e_pipeline.py -v` | Validates complete lifecycle with mock agents, Langfuse tracing, and CLI execution. |

---

## 3. Live Release Gate Demonstrations

### A. Approved Release (Compliant Agent -> Exit Code 0)
Run the evaluation against the compliant candidate agent:
```bash
pytest tests/eval/test_agent_evaluation.py --suite=expected --agent-endpoint="mock://compliant" --gate --baseline-metrics="benchmarks/baseline_v1_metrics.json"
```
**Expected Outcome:**
- Terminal prints `[PASS] STATUS: APPROVED`.
- Exits with return code `0`.
- Generates `RELEASE_GATE.md` and `reports/eval_report.json`.

### B. Blocked Release (Regressed Agent -> Exit Code 1)
Run the evaluation against a candidate with regressions:
```bash
pytest tests/eval/test_agent_evaluation.py --suite=expected --agent-endpoint="mock://regressed" --gate --baseline-metrics="benchmarks/baseline_v1_metrics.json"
```
**Expected Outcome:**
- Terminal prints `[FAIL] STATUS: RELEASE BLOCKED`.
- Exits with return code `1` (blocking CI/CD deployment).
- Logs critical regression violations (e.g., F1 dropped by >3%).

### C. Zero-Tolerance Adversarial Security Check (P0)
Run the 30-case adversarial jailbreak and prompt injection attack suite:
```bash
pytest tests/eval/test_agent_evaluation.py --suite=adversarial --agent-endpoint="mock://compliant" --gate --baseline-metrics="benchmarks/baseline_v1_metrics.json"
```
**Expected Outcome:**
- 30 adversarial injection attacks evaluated.
- 100% refusal rate required. Zero prompt leaks permitted.

---

## 4. Evaluating a Live External HTTP REST Agent

To evaluate your live agent hosted over HTTP/REST:
```bash
pytest tests/eval/test_agent_evaluation.py \
  --agent-endpoint="http://localhost:8000/v1/chat" \
  --suite="all" \
  --gate \
  --gate-threshold=0.03 \
  --baseline-metrics="benchmarks/baseline_v1_metrics.json" \
  --report-out="reports/my_agent_eval.json"
```

The agent endpoint should accept:
```json
POST /v1/chat
{
  "test_case_id": "TC-EXP-001",
  "prompt": "What is my checking account balance?",
  "context": ["Account #1001 balance is $1,250.00."],
  "metadata": {}
}
```
And respond with JSON:
```json
{
  "response": "Your checking account balance is $1,250.00.",
  "extracted_entities": [{"name": "balance", "value": "$1,250.00"}]
}
```

---

## 5. Inspecting Generated Reports

After any evaluation run with `--gate`, inspect the generated artifacts:

1. **GitHub PR Markdown Report (`RELEASE_GATE.md`):**
   Formatted comparison tables with status badges (`🟢 PASS`, `🔴 FAIL`, `🟡 WARN`), deltas, and failure logs.
2. **Machine-Readable JSON Summary (`reports/eval_report.json`):**
   Full structured JSON output including candidate summary, baseline comparison, and gating decisions.

---

## 6. Observability & Langfuse Sync

To stream traces, spans, and rubric scores to Langfuse:
```bash
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_HOST="https://cloud.langfuse.com"

pytest tests/eval/test_agent_evaluation.py --agent-endpoint="mock://compliant" --langfuse-sync
```
If credentials are not set, telemetry gracefully logs a non-blocking warning without failing the test run.

---

## 7. CI/CD Integration

The repository includes a ready-to-run GitHub Actions pipeline in [`.github/workflows/agent_release_gate.yml`](.github/workflows/agent_release_gate.yml) that:
1. Verifies dataset checksum integrity.
2. Executes full unit test suite.
3. Runs the evaluation and release gate.
4. Publishes reports as workflow artifacts and posts status comments on Pull Requests.
