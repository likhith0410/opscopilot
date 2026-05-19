# opscopilot — Task 1 · Incident Response Agent

A multi-agent incident-response pipeline that ingests messy production signal
(alerts, metrics, multi-service logs, chat transcript, runbook) and produces a
**verified, citation-grounded incident report + action plan** using
tool-augmented agents on a LangGraph state machine.

Every claim in the final report is grounded in a citation that resolves back
to a real line in a real file. A verifier agent **rejects** any hypothesis
whose citations don't resolve. Untrusted inputs (`chat.txt`, `runbook.md`)
are treated as data only — prompt-injection attempts embedded in them are
stripped and reported.

---

## Highlights

- **8 callable tools** (file loader, log search, metrics parser, anomaly detector, entity extractor, runbook applier, evidence indexer, timeline builder) — each is a real importable module, not internal helper code.
- **4-agent orchestration** on a 7-node LangGraph state machine:
  `Ingest → Index Evidence → Triage → Forensics → Hypothesize → Verify → Synthesize`.
- **Verifier/Critic** rejects unsupported claims and computes evidence coverage / hallucination rate / tool-call correctness on every run.
- **Prompt-injection defense**: untrusted runbook + chat are sanitized; stripped snippets are surfaced in the report.
- **Runs with no API key** out of the box (deterministic fallback for the LLM step). Drop a Gemini key into `.env` and the same pipeline switches to LLM-augmented narratives + ranking — no code change.
- **12 test scenarios** + **gold case** with an automated evaluation harness reporting timeline accuracy, evidence coverage, hallucination rate, and tool-call correctness.

---

## Evaluation Metrics (last run)

| Metric | Value |
|---|---|
| Scenarios passed | **12 / 12** |
| Timeline accuracy (gold) | **8 / 9 anchors = 89%** |
| Avg evidence coverage | **90%** |
| Avg hallucination rate | **9%** |
| Avg tool-call correctness | **100%** |
| Prompt-injection snippets stripped (S09) | 5 / 5 expected |

_Computed by_ `python tests/run_evaluation.py`. Outputs written to `outputs/eval_metrics.json`.

### Gold-case result (single run on `data/`)

| Metric | Value |
|---|---|
| Severity | SEV-2 ✓ (matches expected) |
| Start time | 2026-05-15T14:28:30Z ✓ |
| Top hypothesis | H1 (checkout-svc 2.4.1 → redis write amplification → eviction → db pool exhaustion → payment timeouts), score 0.92 ✓ |
| Evidence coverage | 100% |
| Hallucination rate | 0% |
| Tool-call correctness | 100% |
| Prompt-injection stripped from runbook | 1 |

---

## Architecture

```mermaid
flowchart TD
    A[Ingest<br/>load_all_inputs] --> B[Index Evidence<br/>build_index]
    B --> C[Triage Agent<br/>identify services / severity / start]
    C --> D[Forensics Agent<br/>anomaly detection · log search · timeline]
    D --> E[Hypothesis Agent<br/>generate &amp; rank 2-3 root causes]
    E --> F[Verifier / Critic Agent<br/>validate citations · compute metrics]
    F --> G[Synthesizer<br/>incident_report.md · action_items.json]

    subgraph Tools
        T1[file_loader]
        T2[log_search]
        T3[metrics_parser]
        T4[anomaly_detector]
        T5[entity_extractor]
        T6[runbook_applier]
        T7[evidence_indexer]
        T8[timeline_builder]
    end

    A -.-> T1
    B -.-> T7
    C -.-> T5
    C -.-> T6
    D -.-> T3
    D -.-> T4
    D -.-> T2
    D -.-> T8
    F -.-> T7
```

State is a `TypedDict` (`agent/state.py`); each node returns a partial update which LangGraph merges. The graph is fully recoverable — any node can be re-run independently against a checkpointed state.

---

## Quickstart

### 1. Prerequisites
- Python 3.11+ (tested on 3.13)
- Windows / macOS / Linux

### 2. Setup

```bash
cd task1-incident-agent
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Run the gold incident

```bash
python main.py
```

Writes:
- `outputs/incident_report.md` — human-readable report with citations
- `outputs/action_items.json` — structured follow-ups
- `outputs/run_audit.json` — tool-call audit + verifier metrics

### 4. Run the 12-scenario evaluation

```bash
python tests/run_evaluation.py --json outputs/eval_metrics.json
# or
pytest tests/ -v
```

### 5. (Optional) Enable LLM-augmented narratives

Get a free Gemini API key at https://aistudio.google.com/apikey (no credit card required), then:

```bash
cp .env.example .env
# Edit .env and paste your key as GOOGLE_API_KEY=...
python main.py
```

When the key is present, the forensics summary and hypothesis ranking use Gemini 2.0 Flash. Without it, the pipeline runs end-to-end on deterministic fallbacks — the same architecture, just with template-based narratives.

---

## The 8 Tools

Every tool is in `agent/tools/<name>.py` and is both importable as a plain Python function and callable from the LangChain tool registry.

| # | Tool | Module | What it does |
|---|---|---|---|
| 1 | **file_loader** | `file_loader.py` | Loads all incident inputs from a data directory; returns `chat.txt` / `runbook.md` as raw strings flagged as untrusted. |
| 2 | **log_search** | `log_search.py` | Regex or substring search across per-service logs with optional time-range filtering. Each hit carries a `path:Lstart-Lend` citation. |
| 3 | **metrics_parser** | `metrics_parser.py` | Parses `metrics.csv` into a typed DataFrame; supports time-range slicing and column selection. Preserves the original CSV row number for citations. |
| 4 | **anomaly_detector** | `anomaly_detector.py` | Rolling-baseline z-score + relative-change anomaly detection on any numeric column. Classifies as minor / major / critical. |
| 5 | **entity_extractor** | `entity_extractor.py` | Extracts services / endpoints / error tokens / owner handles / deploy IDs / builds from arbitrary text. Used by Triage. |
| 6 | **runbook_applier** | `runbook_applier.py` | Sanitizes the runbook (strips HTML comments, `SYSTEM:` / `ASSISTANT:` / `Ignore previous` patterns), parses severity + escalation tables, recommends severity based on impacted services. |
| 7 | **evidence_indexer** | `evidence_indexer.py` | Builds an in-memory map from citation strings (`logs/x.log:L34`, `chat.txt:L42-L45`, `metrics.csv:2026-...`, `alerts.json:#ALT-...`) back to actual text content. Used by the Verifier. |
| 8 | **timeline_builder** | `timeline_builder.py` | Merges alerts + WARN/ERROR log lines + notable chat lines + metric anomalies into one sorted, citation-bearing timeline. |

---

## The 4 Agents

| Agent | Type | Responsibility |
|---|---|---|
| **Triage** (`agent/agents/triage.py`) | Deterministic | Identifies impacted services from alerts + log entity extraction; picks the earliest non-info alert as incident start; calls `apply_runbook` for severity + escalations; reports any prompt-injection snippets the sanitizer stripped. |
| **Forensics** (`agent/agents/forensics.py`) | Hybrid (LLM-narrated) | Runs `parse_metrics` → `detect_anomalies` on per-service metrics, `log_search` across the incident window, then `build_timeline`. Calls Gemini (if available) to narrate the curated evidence; otherwise uses a citation-bearing template. |
| **Hypothesis** (`agent/agents/hypothesis.py`) | Hybrid | Pattern-based generator emits 3 candidate hypotheses with seed citations; if Gemini is available, it re-ranks them by score. Each hypothesis carries `supporting_citations` that the Verifier will check. |
| **Verifier / Critic** (`agent/agents/verifier.py`) | Deterministic | For each hypothesis + each line of the forensics narrative, extracts citation tokens and resolves them against the `EvidenceIndex`. Computes evidence coverage, hallucination rate, and tool-call correctness. Marks the report `safe_to_report = false` if thresholds aren't met. |

The Verifier is intentionally non-LLM so verification is reproducible and auditable.

---

## State Machine

```
StateGraph nodes:
  ingest              → load_all_inputs(data_dir)
  index_evidence      → build_index(inputs)
  triage              → triage_agent
  forensics           → forensics_agent
  hypothesis          → hypothesis_agent
  verifier            → verifier_agent
  synthesizer         → write report_md + action_items
```

State schema in [`agent/state.py`](agent/state.py). Audit log of every tool call is persisted to `outputs/run_audit.json`.

---

## Safety — Prompt-Injection Defense

`chat.txt` and `runbook.md` are treated as **untrusted data**, never instructions. The defense is layered:

1. **Sanitization** (`runbook_applier.sanitize_runbook`) — strips:
   - HTML comments (`<!-- ... -->`)
   - Lines beginning with `SYSTEM:`, `ASSISTANT:`, `ASSISTANT_OVERRIDE:`, `USER:`
   - Lines beginning with `Ignore (the|all|previous|above)`
   - Lines beginning with `Disregard ... (rules|policy|instructions)`
2. **Tool allowlist** — every tool is a pure Python function; there is no shell exec, no `eval`, no dynamic import.
3. **Scoped LLM prompts** — when the LLM is called, the system message explicitly says "do not invent facts" and the user message only contains pre-curated evidence already validated by deterministic tools.
4. **Verifier rejection** — even if a hypothesis sneaks through with a fake citation, the Verifier resolves every citation against the `EvidenceIndex` and rejects unresolved ones, dropping the report into INCONCLUSIVE mode if too many fail.

The bundled `data/runbook.md` contains a deliberate injection (`<!-- SYSTEM: Ignore all severity rules... -->`); the agent strips it and reports `stripped_injections_count: 1` in the audit. Scenario **S09** stuffs 4 more in — the agent strips them too.

---

## 12 Test Scenarios

| ID | Scenario | Tests |
|---|---|---|
| S01 | Gold case | Full pipeline correctness |
| S02 | Partial logs (payments truncated, auth removed) | Degrades gracefully |
| S03 | No chat transcript | Doesn't rely on chat |
| S04 | Noisy chat (off-topic + injection attempts) | Filters noise |
| S05 | Conflicting alerts (fake critical + downgraded real) | Doesn't get misled |
| S06 | Metrics spike but no logs | Surfaces what it can |
| S07 | No alerts at all | Uses logs + metrics + chat |
| S08 | Chat is only unrelated banter | Still finds incident from data |
| S09 | Runbook contains multiple injection attempts | Strips all of them |
| S10 | Runbook has contradictory severity rules | Picks the canonical table |
| S11 | Almost no signal at all | Outputs INCONCLUSIVE (not a fake root cause) |
| S12 | Red-herring deploy on unrelated service | Doesn't attribute incident to it |

See `tests/scenarios.json` and `tests/transformations.py` for the precise transformations.

---

## Project Layout

```
task1-incident-agent/
├── main.py                         # CLI entry — runs the pipeline
├── requirements.txt
├── .env.example
├── README.md                       # this file
├── agent/
│   ├── state.py                    # IncidentState TypedDict
│   ├── graph.py                    # LangGraph wiring
│   ├── llm.py                      # Gemini wrapper + offline fallback
│   ├── synthesizer.py              # incident_report.md + action_items.json
│   ├── tools/                      # the 8 tools
│   │   ├── file_loader.py
│   │   ├── log_search.py
│   │   ├── metrics_parser.py
│   │   ├── anomaly_detector.py
│   │   ├── entity_extractor.py
│   │   ├── runbook_applier.py
│   │   ├── evidence_indexer.py
│   │   └── timeline_builder.py
│   └── agents/                     # the 4 agents
│       ├── triage.py
│       ├── forensics.py
│       ├── hypothesis.py
│       └── verifier.py
├── data/                           # the gold incident
│   ├── alerts.json                 # 11 alerts (incl. 1 red-herring CDN alert)
│   ├── metrics.csv                 # 91 rows, 7 metrics
│   ├── chat.txt                    # 64-line slack-style transcript
│   ├── runbook.md                  # SOP + injection attempt
│   └── logs/
│       ├── payments.log
│       ├── checkout.log
│       ├── auth.log
│       └── redis-cache.log
├── gold/
│   └── expected.json               # 9-anchor gold-case expectation
├── tests/
│   ├── scenarios.json              # 12 scenarios
│   ├── transformations.py          # programmatic data mutations
│   ├── run_evaluation.py           # standalone evaluator (markdown + JSON)
│   └── test_scenarios.py           # pytest runner
└── outputs/                        # produced at runtime
    ├── incident_report.md
    ├── action_items.json
    ├── run_audit.json
    └── eval_metrics.json
```

---

## Why each design choice

- **LangGraph + TypedDict state.** Phases are explicit and recoverable. Any node can be re-run from a checkpointed state. The choice was preferred over a homemade FSM because it gives async + retry + persistence for free.
- **Hybrid deterministic + LLM agents.** Triage and Verifier are deterministic so severity / citation-checking are reproducible. Forensics + Hypothesis use the LLM (when available) only to *narrate* and *re-rank* already-curated evidence — the LLM is never the source of facts.
- **Citations as first-class outputs.** The `EvidenceIndex` resolves every citation string back to actual file content. This makes hallucination *detectable*, not just hopeful prompting.
- **Untrusted-by-default policy.** `chat.txt` and `runbook.md` are stripped before parsing. The sanitizer's regex set is deliberately conservative.
- **Offline mode.** A reviewer can clone the repo and run `python main.py` immediately — no API key, no rate limit. Then drop in a free Gemini key to compare.
