# Step-by-Step Setup Walkthrough (beginner-friendly)

This walks you through every click to get the n8n workflow running and capture
the 4 required screenshots. Budget ~45–60 minutes (most of it is one-time
account setup). Do the phases in order.

> Tick each box as you go: `[ ]` → `[x]`.

---

## Phase 0 — Install Docker (one time)

- [ ] Download **Docker Desktop**: https://www.docker.com/products/docker-desktop/
- [ ] Install it, then **launch it** and wait until the whale icon in your
  system tray says "Docker Desktop is running".
- [ ] Verify: open **PowerShell** and run:
  ```powershell
  docker --version
  ```
  You should see a version number. If "command not found", reopen PowerShell
  after Docker finishes starting.

---

## Phase 1 — Start n8n

- [ ] In PowerShell:
  ```powershell
  cd C:\Lik\Assignments\opscopilot\task2-n8n-workflow
  copy .env.example .env
  docker compose up -d
  ```
- [ ] Open your browser to **http://localhost:5678**
- [ ] Create the local owner account (any email/password — it's only stored on
  your machine). You're now in the n8n editor.

> Leave this running. We'll come back to fill in `.env` and import workflows.

---

## Phase 2 — Google Sheets (storage)

### 2a. Create the sheet
- [ ] Go to https://sheets.google.com → **Blank spreadsheet**.
- [ ] Rename it `opscopilot-leads` (top-left).
- [ ] Rename the first tab (bottom-left) to **`Leads`**, and in **row 1** type
  these headers, one per column (A, B, C, …):
  ```
  idempotency_key   received_at   name   email   company   company_source   product   urgency   message   status
  ```
- [ ] Click **+** (bottom-left) to add a second tab named **`DeadLetter`**, with
  row-1 headers:
  ```
  received_at   name   email   company   product   urgency   message   error_reason   stage
  ```
- [ ] Copy the **document ID** from the URL. The URL looks like:
  `https://docs.google.com/spreadsheets/d/`**`1AbC...XyZ`**`/edit` — the bold
  part is the ID.
- [ ] Open `task2-n8n-workflow\.env` in a text editor and set:
  ```
  SHEETS_DOC_ID=1AbC...XyZ
  ```

### 2b. Connect Google Sheets in n8n
- [ ] In n8n: left sidebar → **Credentials** → **Add credential** → search
  **"Google Sheets OAuth2 API"** → **Continue**.
- [ ] n8n shows a "Connect my account" button. Follow the prompts to sign in
  with your Google account and allow access.
  - If it asks you to set up Google OAuth manually, follow n8n's guide:
    https://docs.n8n.io/integrations/builtin/credentials/google/oauth-single-service/
    (For a quick local demo, the built-in "Sign in with Google" usually works.)
- [ ] **Important:** name this credential exactly **`Google Sheets account`**
  (top of the credential panel), then **Save**.

---

## Phase 3 — Slack (high-urgency alert + digest)

- [ ] Go to https://api.slack.com/apps → **Create New App** → **From scratch**.
- [ ] Name it `opscopilot`, pick your workspace → **Create App**.
- [ ] Left menu → **Incoming Webhooks** → toggle **On**.
- [ ] Scroll down → **Add New Webhook to Workspace** → choose a channel (e.g.
  `#general` or make a `#leads` channel) → **Allow**.
- [ ] Copy the webhook URL (looks like
  `https://hooks.slack.com/services/T000/B000/xxxx`).
- [ ] In `.env` set:
  ```
  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T000/B000/xxxx
  ```

> No n8n credential needed for Slack — we post to this URL directly.

---

## Phase 4 — Trello (high-urgency ticket)

### 4a. Make a board + list
- [ ] Go to https://trello.com → create a board named `Support Pipeline`.
- [ ] It comes with lists like "To Do". Keep one (e.g. rename to `Incoming`).

### 4b. Get API key + token
- [ ] Go to https://trello.com/power-ups/admin → **New** to create a Power-Up
  (Trello now issues API keys via Power-Ups). Give it any name; you'll get an
  **API key**.
  - Simpler legacy route (if available): https://trello.com/app-key shows the
    key directly.
- [ ] On that page, click the **Token** link to generate a **token** → **Allow**.
- [ ] Keep both the **key** and **token** handy.

### 4c. Find the list ID
- [ ] Open your board in the browser. Copy its URL, and in a new tab open:
  `https://api.trello.com/1/boards/<BOARD_SHORT_ID>/lists?key=<KEY>&token=<TOKEN>`
  - `<BOARD_SHORT_ID>` is the part after `/b/` in your board URL.
- [ ] You'll see JSON listing your lists. Copy the `"id"` of your `Incoming` list.
- [ ] In `.env` set:
  ```
  TRELLO_LIST_ID=<that id>
  ```

### 4d. Connect Trello in n8n
- [ ] n8n → **Credentials** → **Add credential** → search **"Trello API"**.
- [ ] Paste the **API key** and **token**.
- [ ] Name it exactly **`Trello account`** → **Save**.

---

## Phase 5 — SMTP / Email (normal-urgency confirmation)

Using Gmail:
- [ ] Enable 2-Step Verification on your Google account (if not already):
  https://myaccount.google.com/security
- [ ] Create an **App Password**: https://myaccount.google.com/apppasswords →
  pick "Mail" → generate → copy the 16-character password.
- [ ] In `.env` set your from-address:
  ```
  SMTP_FROM_EMAIL=youraddress@gmail.com
  ```
- [ ] n8n → **Credentials** → **Add credential** → search **"SMTP"**:
  - **Host:** `smtp.gmail.com`
  - **Port:** `465`
  - **SSL/TLS:** on
  - **User:** your Gmail address
  - **Password:** the 16-char app password
  - Name it exactly **`SMTP account`** → **Save**.

---

## Phase 6 — Load env + import workflows

- [ ] Apply the `.env` values by restarting n8n. In PowerShell:
  ```powershell
  cd C:\Lik\Assignments\opscopilot\task2-n8n-workflow
  docker compose down
  docker compose up -d
  ```
- [ ] Back in n8n (http://localhost:5678): top-right **⋯ / Import** →
  **Import from File**. Import all three from the `workflows\` folder:
  - `lead-to-support.json`
  - `daily-digest.json`
  - `error-handler.json`
- [ ] Open **`opscopilot — Lead to Support`**. Any node with a red triangle
  needs its credential picked. Click each Google Sheets node → in the
  credential dropdown choose **`Google Sheets account`**. Do the same for the
  Trello node (`Trello account`) and the SMTP node (`SMTP account`).
  (The Slack + digest nodes are HTTP Request nodes — no credential needed.)
- [ ] Click **Save**, then toggle **Active** (top-right) to ON.
- [ ] Click the **Webhook: Lead Intake** node → copy its **Production URL**
  (should be `http://localhost:5678/webhook/lead-intake`).
- [ ] Also open **`opscopilot — Daily Lead Digest (6 PM)`** and toggle it Active.

---

## Phase 7 — Run the samples + capture screenshots

Open a new PowerShell in the task folder:
```powershell
cd C:\Lik\Assignments\opscopilot\task2-n8n-workflow
```

### Screenshot 1 — high-urgency path
- [ ] Run:
  ```powershell
  .\send-payload.ps1 -File sample-payloads\01-valid-high-acme.json
  ```
- [ ] In n8n, open the workflow → **Executions** (left) → click the latest run.
  The Slack→Trello branch should be green.
- [ ] Check your Slack channel (alert posted) and your Trello list (card created).
- [ ] **Capture** the canvas + Slack message + Trello card → save as
  `screenshots\01-high-urgency-path.png`.

### Screenshot 2 — normal path
- [ ] Run:
  ```powershell
  .\send-payload.ps1 -File sample-payloads\02-valid-normal-gmail.json
  ```
- [ ] Check the confirmation email arrived, and the `Leads` sheet has a new row
  with `status = confirmed-emailed`.
- [ ] **Capture** the green run + email + sheet row → `screenshots\02-normal-path.png`.

### Screenshot 3 — dead-letter / failure
- [ ] Run:
  ```powershell
  .\send-payload.ps1 -File sample-payloads\07-invalid-spam-keywords.json
  ```
- [ ] Response should be `400 rejected`; the `DeadLetter` sheet gets a new row
  with an `error_reason`.
- [ ] **Capture** the IF→DeadLetter branch + the DeadLetter row →
  `screenshots\03-dead-letter-path.png`.

### Screenshot 4 — daily digest
- [ ] Open the **Daily Lead Digest** workflow → click **Execute Workflow**.
- [ ] A digest message appears in Slack (counts by urgency/product + top-5).
- [ ] **Capture** the green run + Slack digest → `screenshots\04-daily-digest.png`.

### Bonus — idempotency proof
- [ ] Run:
  ```powershell
  .\send-payload.ps1 -File sample-payloads\09-idempotency-replay.json -Repeat 3
  ```
- [ ] First response `accepted`, next two `duplicate`. The `Leads` sheet has
  exactly **one** row for that key.
- [ ] **Capture** the 3 responses + the single sheet row →
  `screenshots\05-idempotency-proof.png`.

---

## Done

- [ ] All 4 (or 5) screenshots saved in `screenshots\`.
- [ ] Tell Claude "screenshots done" and we'll commit + push them to GitHub.

### Troubleshooting
- **Webhook 404**: make sure the workflow is **Active** and you copied the
  *Production* URL (not the test URL).
- **Sheets node error**: confirm the tab names are exactly `Leads` /
  `DeadLetter` and `SHEETS_DOC_ID` is set, then `docker compose down && up -d`.
- **Slack nothing posts**: re-check `SLACK_WEBHOOK_URL` in `.env` and that you
  restarted n8n after editing `.env`.
- **Stop n8n** when done: `docker compose down` (your data persists).
