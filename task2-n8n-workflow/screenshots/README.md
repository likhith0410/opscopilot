# Screenshots — required evidence

The assignment requires four screenshots. Capture each after running the
matching sample payload, then save it in this folder with the filename shown.
Once saved, they render in the table below automatically.

| # | Filename to save | What to capture | How to produce it |
|---|---|---|---|
| 1 | `01-high-urgency-path.png` | A successful **high-urgency** execution: the workflow canvas with the Slack + Trello branch all green, **plus** the Slack alert message and the Trello card. | Send `sample-payloads/01-valid-high-acme.json`, then open the execution in n8n and screenshot the green path; include the Slack message + Trello card (can be a stitched/side-by-side image). |
| 2 | `02-normal-path.png` | A successful **normal** execution: the SMTP + Sheets-log branch green, plus the received confirmation email and the new `Leads` row with `status=confirmed-emailed`. | Send `sample-payloads/02-valid-normal-gmail.json`. |
| 3 | `03-dead-letter-path.png` | A **rejected** execution: the IF→DeadLetter branch, the `400` response, and the new row in the `DeadLetter` sheet tab with an `error_reason`. | Send `sample-payloads/07-invalid-spam-keywords.json` (or any `05`–`08`). |
| 4 | `04-daily-digest.png` | A **digest** execution: the digest workflow run (all nodes green) and the Slack digest message showing counts by urgency, by product, and top-5 recent. | Open `daily-digest.json`, click **Execute Workflow**, screenshot the run + the Slack message. |

Optional but nice to include:
- `05-idempotency-proof.png` — the terminal showing 3 responses (1 `accepted`, 2 `duplicate`) next to the `Leads` sheet proving only **one** row exists for that key.

## Tips
- PNG keeps text crisp; keep each file under ~1 MB if you can.
- Black out any real API tokens / personal email addresses before committing.
- A single composite image per row (canvas + result side by side) reads best in the README.
