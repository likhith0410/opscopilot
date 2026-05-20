# opscopilot

Two production-flavored automation projects:

1. **[Incident Response Agent](task1-incident-agent/)** — a multi-agent, tool-using
   pipeline (LangGraph) that ingests messy production signal (alerts, metrics,
   multi-service logs, chat, runbook) and produces a **verified,
   citation-grounded incident report + action plan**. Every claim cites real
   evidence; a verifier agent rejects anything unsupported. Untrusted inputs are
   sanitized against prompt injection.

2. **[Lead-to-Support Automation](task2-n8n-workflow/)** — an n8n workflow that
   turns inbound leads (webhook) into a structured support pipeline: validate →
   spam-check → enrich → **idempotent** store → urgency routing (Slack + Trello /
   email) → daily digest, with retries, failure logging, and a dead-letter path.

---

## Project 1 — Incident Response Agent

`python` · `langgraph` · `gemini (optional)` · `pandas`

- **8 callable tools**, **4 agents** (Triage / Forensics / Hypothesis /
  Verifier-Critic) on a **7-node state machine**:
  `Ingest → Index Evidence → Triage → Forensics → Hypothesize → Verify → Report`.
- Every report claim is grounded in a citation (`logs/payments.log:L23`,
  `metrics.csv:2026-05-15T14:31:00Z`, `alerts.json:#ALT-...`) that resolves back
  to real file content. Unsupported citations are rejected by the verifier.
- **Runs with no API key** (deterministic fallback). Drop in a free Gemini key
  for LLM-augmented narration — same architecture, no code change.
- **Gold case + 12 test scenarios** with an evaluation harness.
  Last run: **12/12 scenarios pass**, 89% timeline accuracy, 90% evidence
  coverage, 9% hallucination, 100% tool-call correctness.

```bash
cd task1-incident-agent
python -m venv .venv && .venv\Scripts\activate     # (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
python main.py                                     # writes outputs/incident_report.md + action_items.json
pytest tests/ -v                                   # 12 scenarios
```

Full details: **[task1-incident-agent/README.md](task1-incident-agent/README.md)**

---

## Project 2 — Lead-to-Support Automation (n8n)

`n8n` · `google sheets` · `slack` · `trello` · `smtp`

- Webhook intake → validation + spam detection → company enrichment →
  **idempotent** Google Sheets store → urgency routing.
- **High urgency** → Slack alert + Trello card. **Normal** → confirmation email
  + status log.
- **Daily 18:00 digest** to Slack (counts by urgency, by product, top-5 recent).
- **Reliability**: idempotency (replay 3× → 1 record), retries with backoff,
  dead-letter sheet for both validation failures and runtime errors.
- 3 importable workflows + 10 sample payloads + Docker setup + replay scripts.

```bash
cd task2-n8n-workflow
docker compose up -d                               # n8n at http://localhost:5678
# import workflows/, wire credentials (see README), then:
./send-payload.sh sample-payloads/09-idempotency-replay.json 3   # proves idempotency
```

Full setup + screenshot guide: **[task2-n8n-workflow/README.md](task2-n8n-workflow/README.md)**

---

## Repository layout

```
opscopilot/
├── task1-incident-agent/     # LangGraph multi-agent incident pipeline (Python)
│   ├── agent/                #   8 tools + 4 agents + state machine
│   ├── data/                 #   gold incident inputs
│   ├── gold/ tests/          #   gold case + 12 scenarios + evaluator
│   └── README.md
└── task2-n8n-workflow/       # n8n lead-to-support automation
    ├── workflows/            #   3 importable workflow JSONs
    ├── sample-payloads/      #   10 sample webhook payloads
    ├── screenshots/          #   evidence (see guide)
    └── README.md
```

## Design principles shared by both

- **Grounding over guessing.** Project 1 makes every claim cite resolvable
  evidence; Project 2 makes every store idempotent and every failure traceable.
- **Reproducible.** Project 1 runs end-to-end with no cloud credentials;
  Project 2 ships Docker + sample payloads so the whole flow is replayable.
- **Defensive.** Untrusted text is sanitized (Project 1); retries + dead-letter
  contain failures (Project 2).
