# Screenshots — Evidence of the Live Pipeline

All four required flows captured from a live run (local n8n + Google Sheets +
Slack + Trello + Gmail SMTP). Each path shows the n8n execution **plus** the
real side-effect it produced.

---

## 1. High-urgency path → Slack alert + Trello card

The lead is validated, enriched, stored, and routed to the **high-urgency**
branch, which posts a Slack alert and creates a Trello card.

**Execution (all green):**

![High-urgency execution](01-high-urgency-path.png)

**Slack alert:**

![Slack alert](01b-slack-alert.png)

**Trello card created (name + company auto-filled):**

![Trello card](01c-trello-card.png)

---

## 2. Normal path → confirmation email + status logged

A normal-urgency lead routes to the **normal** branch: a confirmation email is
sent and the lead's status is logged in the `Leads` sheet.

**Execution (normal branch green):**

![Normal execution](02-normal-path.png)

**Confirmation email received:**

![Confirmation email](02b-confirmation-email.png)

**Lead row in the `Leads` sheet:**

![Leads sheet row](02c-sheet-row.png)

---

## 3. Dead-letter path → validation failure logged

Spam / malformed leads are rejected with a `400` and written to the dedicated
`DeadLetter` sheet tab with the failure reason — separate from the `Leads` table.

**Execution (IF → DeadLetter → Respond 400):**

![Dead-letter execution](03-dead-letter-path.png)

**DeadLetter sheet (rejected leads with `error_reason`):**

![DeadLetter sheet](03b-deadletter-sheet.png)

---

## 4. Daily digest → Slack summary

The scheduled digest (18:00 daily, also runnable on demand) reads the day's
leads and posts a Slack summary: counts by urgency, by product, and the top-5
most recent.

**Digest execution (all green):**

![Digest execution](04b-digest-execution.png)

**Slack digest message:**

![Daily digest](04-daily-digest.png)

---

## How each was produced

| # | Path | Trigger |
|---|------|---------|
| 1 | High-urgency | `POST` a `"urgency":"high"` payload → Slack + Trello |
| 2 | Normal | `POST` a `"urgency":"normal"` payload → email + sheet log |
| 3 | Dead-letter | `POST` a spam / malformed payload (e.g. `sample-payloads/07-invalid-spam-keywords.json`) → `400` + DeadLetter row |
| 4 | Daily digest | Open `daily-digest.json` → **Execute Workflow** → Slack summary |

Idempotency is also demonstrable: replaying the same payload returns
`{"status":"duplicate"}` and stores only one row (see the README's idempotency
section).
