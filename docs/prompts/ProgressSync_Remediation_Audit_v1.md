# ProgressSync AI (SIH26122) — Consolidated Remediation Audit v1

**Audience:** Claude Pro / Claude Code (the implementer). **Owner:** Dharmesh (Stride Sense).
**Status of this file:** v1.1. Static diagnosis is done (§1.4): build path, ownership and revision are ruled
out as causes. The confirmed MiniLM root cause still needs one runtime result (`/api/v1/ml/status` on the live
URL). All other parts are ready to implement.

---

## 0. How to use this file (read first)

1. Read the whole file before writing code. Then implement **in the order of §9**, one workstream (WS) per
   branch/PR, committing small.
2. **Do not touch the currently deployed release.** It is the fallback submission. All work happens on a new
   branch (`v2-remediation`) and is deployed to a **separate** Elastic Beanstalk environment. Cut over only
   when the §10 gates pass.
3. **Never weaken the decision-safety core.** Do not change matching weights, confidence/margin thresholds,
   the "human confirms before schedule writes" rule, or the negation/regression guards
   (audit F-01 / F-02). After *every* change run the full test suite and the frozen benchmark
   (`scripts/run_benchmark.py`). Requirement: all tests pass, **0 silent errors**, auto-match precision unchanged.
4. Do not claim a feature works because code exists. Each WS has **acceptance criteria**; report the actual
   request/response or a description of what rendered for each one.
5. If a fix would require something outside a WS's scope (new AWS resource, new paid service, a decision
   about product behaviour), **stop and ask** instead of guessing.

---

## 1. WS1 — MiniLM (semantic model) not working in the deployed app  **[P0]**

### 1.1 What is known (verified in code)
- Model: `sentence-transformers/all-MiniLM-L6-v2`, revision pinned in `backend/app.py`
  (`SEMANTIC_MODEL_REVISION`, first 12 chars `1110a243fdf4`).
- Loaded **lazily** on first use by `get_semantic_model()` with `local_files_only=True`. There is no network
  fallback by design.
- `get_semantic_model()` converts only `OSError` into `SemanticModelMissing`. **Any other exception type
  propagates as an unhandled 500.** `GET /api/v1/ml/status` catches only `SemanticModelMissing`, so a
  non-OSError failure makes the status endpoint itself 500 instead of reporting the reason.
- `/api/v1/ml/status` reports `semantic_model_available` (true/false). It also reports
  `reranker_enabled`, which is **false by default** (`PROGRESSSYNC_USE_RERANKER=false`).
- Deployment is a multi-stage Docker build: model provisioned in the build stage, then copied into a slim
  runtime image running as a **non-root** user (per the handoff report §12). Semantic weight in the fused
  score is 0.25.
- The handoff report recorded "Semantic matching ✅ Working" and live scores such as 0.965 / 0.907 at deploy
  time. So either it worked and later broke, or the reported symptom is not what it seems (see H0).

### 1.2 Ranked hypotheses
| ID | Hypothesis | Why plausible | Decisive check |
|----|-----------|---------------|----------------|
| H0 | **Not actually broken.** The symptom is the *reranker* showing "disabled", or a UI label reading the wrong field. | Reranker is off by default; "ML disabled" reads like "MiniLM broken". | `GET /api/v1/ml/status`: is `semantic_model_available` true? |
| H1 | **HF cache path mismatch.** Model cached under the build user's home; runtime user/env looks elsewhere. `HF_HOME` / `HF_HUB_CACHE` / `SENTENCE_TRANSFORMERS_HOME` not set to the copied path. | Most common cause of "works in build, `local_files_only` fails at runtime". | Container: `python -c` load with `local_files_only=True`; `echo $HF_HOME`; `find / -type d -name snapshots`. |
| H2 | **Revision/snapshot mismatch.** Provisioned revision ≠ `SEMANTIC_MODEL_REVISION`, or `refs/`/`snapshots/` structure broken by the COPY. | Pinned revision + offline mode means an exact snapshot dir must exist. | `ls -la <cache>/models--sentence-transformers--all-MiniLM-L6-v2/{refs,snapshots}`; compare to constant. |
| H3 | **Permissions.** Copied cache is root-owned/unreadable by the non-root runtime user. | Multi-stage copy + `USER` switch. | `id`; `ls -ln` on the cache; try reading a file as the runtime user. |
| H4 | **Non-OSError load failure** (library incompatibility: `transformers 5.x` / `sentence-transformers 6.x` / torch CPU, missing shared lib). | Pinned new majors; only OSError is handled → raw 500. | Full traceback from the direct `python -c` load; container logs. |
| H5 | **Cold-start / resource failure.** First request triggers a ~90 MB model load + torch init; request times out at the proxy, or a worker is OOM-killed. | Lazy load means the first user pays the cost; small instance. | Time the first `POST /api/v1/reports` after restart; `free -m`, `dmesg | grep -i oom`, EB nginx/web logs. |
| H6 | **Wrong image/env.** EB is running an image tag without the model, or an env var (e.g. `HF_HUB_OFFLINE`) differs from the tested container. | Redeploys during hardening. | Compare deployed image digest to the one tested locally; EB env config. |

### 1.3 Required code changes regardless of root cause (hardening)
These make the failure visible and prevent a repeat:
1. **Eager load at startup** (FastAPI lifespan/startup): load the model and run one throwaway
   `encode()` so cold-start cost is paid before traffic. Log model name, revision, cache path, load seconds.
2. **Catch broadly in `get_semantic_model()`**: wrap load in `except Exception`, keep a module-level
   `_semantic_error` string, raise `SemanticModelMissing` with the real reason. Never leave a bare 500.
3. **`/api/v1/ml/status`**: always return 200 with `semantic_model_available`, `semantic_error` (string or null),
   `semantic_cache_path`, `semantic_load_seconds`, and a clearly separate `reranker_*` block. Do not change
   the existing field names (tests and the UI depend on them); only add fields.
4. **Readiness**: make the health endpoint used by Elastic Beanstalk fail (503) when the semantic model is
   unavailable, so a broken image never goes "Green".
5. **UI**: show a distinct "Semantic model: available / unavailable (reason)" indicator, separate from the
   reranker toggle, so H0 can never recur.
6. **Docker**: set `ENV HF_HOME=/opt/hf` (or equivalent) **in both build and runtime stages**, provision into
   that path, `chown` it to the runtime user, set `HF_HUB_OFFLINE=1` at runtime, and add a **build-time
   verification step** (`RUN python -c "...local_files_only=True..."` as the runtime user) so the image cannot
   build if the model is not loadable.
7. **Test**: add a test that asserts `/api/v1/ml/status` semantic fields and that a paraphrased report
   produces a non-zero semantic component.

### 1.4 Diagnostic results (paste here, then apply the matching cure)
**Static findings from the Copilot diagnostic (verified against the repo):**
- The build stage provisions the pinned model into `/opt/progresssync-model` (full model saved as real
  files, not a symlinked HF cache). The runtime stage sets `PROGRESSSYNC_MODEL_PATH=/opt/progresssync-model`,
  copies that directory, and runs `chown -R progresssync:progresssync /app /opt/progresssync-model` before
  switching to UID 10001. No `HF_*` variables are used or needed.
- `SEMANTIC_MODEL_REVISION` in `backend/app.py` and the revision used by `scripts/provision_model.py` are the
  same full hash (`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`).
- Loader is lazy (lifespan only calls `init_db()`), single Uvicorn worker, no timeout config, no
  `.ebextensions` / `.platform` / `Procfile` / `Dockerrun.aws.json` overrides.
- Only `OSError` is translated to `SemanticModelMissing` (503). Any other exception from
  `SentenceTransformer(...)` escapes as a raw 500, and `/api/v1/ml/status` 500s with it.
- Existing `eb-tail.txt`: container started, image ~1.53 GB, a later report request returned 200, but no
  model-load line appears, so it does not prove the model is available.

**Hypotheses now RULED OUT:** H1 (cache path mismatch), H2 (revision mismatch), H3 (permissions).

**Hypotheses still OPEN (in this order):**
1. **H0** — model is actually fine; the symptom is the reranker showing "disabled" or a UI label.
2. **H7 (new) — deployed bundle ≠ working tree.** `eb deploy` packages the last **commit**, not uncommitted
   files (26 files were uncommitted at audit time). The live app may be running older code or a different
   image than the Dockerfile that Copilot read. Compare the deployed commit/app version label to `git log`.
3. **H4** — non-OSError failure while constructing the model (library incompatibility, malformed saved
   model). Needs the full traceback from the runtime-user load command.
4. **H5** — first-request cold load slow or OOM on the instance.

**Decisive check (10 seconds, do this first):** `GET /api/v1/ml/status` on the live URL.
- `semantic_model_available: true` → MiniLM is working. Fix the UI/label (H0) and add the hardening in §1.3.
- `false` or a 500 → run the container load command and paste the traceback; apply the matching cure
  (H7 redeploy from the correct commit; H4 fix the failing dependency/artifact; H5 warm-up at startup and a
  larger instance).

**Root cause (fill in after the ml/status result):** ______
**Cure applied:** ______

### 1.5 Acceptance criteria
- `GET /api/v1/ml/status` on the deployed URL returns `semantic_model_available: true` and no error.
- A paraphrase test on the **live** URL (report wording that shares no identifier and few keywords with the
  activity) returns a candidate with a non-zero semantic component; scores in the evidence panel are sensible.
- Container restart → first request is fast (no cold-load timeout); startup log shows the model load line.
- EB health goes non-Green if the model is deliberately removed (verify once in the staging env).
- Full tests + benchmark unchanged.

---

## 2. WS2 — Dynamic multi-plant context (OIL loads any plant's blueprint)  **[P1]**

### 2.1 Current state (verified in code — more capable than the UI suggests)
- Backend is **already project-scoped**: every endpoint takes `project_id`; the UI has a project selector;
  the Time Agent session is keyed per project; `POST /api/v1/projects/{id}/schedule/import` accepts CSV/XLSX.
- But onboarding a new plant is poor:
  - No "create plant" flow. Import does `INSERT OR IGNORE INTO projects` with the name **"Project N"**; no
    plant name, code, or location metadata.
  - The seeded **"OIL Demo Project"** is auto-created on init; the demo is effectively one plant.
  - Import requires **exact** column names (`activity_code, description, planned_start, planned_finish,
    discipline`); no mapping for real exports (Primavera/MSP headers differ).
  - `DISCIPLINES` is a hard-coded set of 7; an unknown discipline rejects the row.
  - The terminology map (`data/terminology_map.v1.yaml`, synced into one global table) is **global**, not
    per-plant, so one plant's slang can bleed into another's matching.
  - No dry-run/preview; errors are reported after partial processing.

### 2.2 Target behaviour
Planner creates a plant → uploads its blueprint (CSV/XLSX; XER as a stretch goal) → maps columns → previews
validation → confirms → the whole app (matching, Time Agent, CPM, analytics, audit, memory) switches context
to that plant. Two plants coexist with **zero cross-contamination**.

### 2.3 Changes
1. **Data model**: extend `projects` with `plant_code` (unique), `name`, `location`, `created_by`,
   `created_at`, optional `notes`. Migrate existing rows safely (idempotent migration in `init_db`).
2. **API**: `POST /api/v1/projects` (create), `PATCH /api/v1/projects/{id}`, `GET /api/v1/projects` returns the
   new fields. Keep the existing import endpoint working (backwards compatible).
3. **Import wizard API**: `POST /api/v1/projects/{id}/schedule/import/preview` (dry-run: detect headers,
   suggest column mapping, return row counts, per-row errors, unknown disciplines, dependency/cycle check,
   **writes nothing**); then the existing import endpoint accepts an optional `column_map` JSON.
   Cycle check must reuse the existing `cpm_state`/`ScheduleCycle` logic.
4. **Configurable disciplines**: keep the 7 defaults; let an import map unknown discipline values to an
   existing discipline or add a new per-plant discipline (stored per project). Do not silently drop rows.
5. **Per-plant terminology**: add nullable `project_id` to `terminology_map` (NULL = global base). Matching
   uses `global ∪ plant`, plant entries winning on conflict. Provide `POST /api/v1/projects/{id}/terminology`
   and a simple UI table. Keep the YAML as the source of truth for the global base.
6. **Derived plant vocabulary**: on import, derive location/area/unit vocabulary from the plant's own
   activities so location matching is not tied to the demo plant's naming.
7. **UI**: "New plant" dialog; import wizard (upload → column mapping → preview → confirm); project selector
   shows plant name/code; empty-state for a plant with no schedule; clear banner of the active plant on every
   screen. Time Agent prompts/answers must include the active plant name.
8. **Second demo plant**: add a small, structurally different fixture (different naming, different
   locations, one extra discipline) under `data/` to prove dynamic loading. Do not remove the original seed.

### 2.4 Acceptance criteria
- Create plant B via UI, import its file with non-default headers via the mapping step, see the preview, confirm.
- A report submitted while plant B is active **never** returns an activity from plant A (add an automated
  test that asserts this across many reports) and vice-versa.
- Plant-specific slang added for B does not change matching for A (test).
- Bad files (missing columns, cycle, duplicate codes, unknown discipline) are rejected or flagged at preview
  with nothing written.
- Original benchmark on the original plant is unchanged.

---

## 3. WS3 — Worker (ground-level) POV and WhatsApp intake  **[P1, highest risk]**

### 3.1 Current state (verified)
- The web app is a **planner/supervisor control-room console**: review queue, confirm/reject, CPM, analytics,
  audit. Field input exists (Ingest text/voice/bulk, Time Agent chat) but only inside that same console with
  the same shared token.
- **There is no WhatsApp/Twilio/webhook code anywhere**, and **no user/role concept** (a single shared bearer
  token; the actor is a free-text string). The worker-side experience is the missing half of the product.

### 3.2 Target behaviour
A field worker sends a plain message (WhatsApp, later voice note) such as "spool XX102 at rack 3 done".
The backend runs the **same** ingest → match → decision pipeline, replies to the worker with the outcome or a
clarifying question, and the planner sees it in the review queue / awaiting-confirmation list. Workers never
see or change the schedule directly.

### 3.3 Changes
1. **Roles (minimum viable)**: introduce `worker` and `planner` roles. Simplest acceptable design: two token
   classes (worker tokens can only call the intake/status endpoints; planner token keeps full access), plus a
   `workers` table (name, phone hash, project_id, active). Actor on events becomes the worker's identity.
2. **Channel-agnostic intake service**: refactor the report-ingest logic so `POST /api/v1/reports` and the
   WhatsApp path call one function. New `source` value `whatsapp`. Do not duplicate matching logic.
3. **WhatsApp webhook**: `GET/POST /api/v1/channels/whatsapp/webhook`.
   - Use **Twilio WhatsApp Sandbox for the demo** (fastest, no Meta business verification) behind an adapter
     interface so Meta WhatsApp Cloud API can be swapped in later.
   - **Verify the provider signature** on every request (reject otherwise). Allow-list sender numbers via the
     `workers` table; unknown numbers get a polite refusal and nothing is written.
   - Map the sender → worker → project; run intake; reply with one short message (matched & awaiting
     confirmation / needs clarification / could not match). Reuse the Time Agent clarification state machine
     for follow-up questions; session key = worker+project.
   - Idempotency on the provider message id (retries must not create duplicate events).
   - Rate-limit per sender. Never echo secrets. Store the phone number **hashed**, not raw, where possible.
4. **Worker mobile-first UI**: a simplified capture screen (text now, voice as stretch), "my recent reports"
   with status, no schedule editing. This is the natural role of the React Native app (see WS4) and/or a
   mobile-first web route.
5. **Hard dependency — HTTPS (WS6)**: WhatsApp providers require a public HTTPS webhook. The current URL is
   plain HTTP. Do WS6 first.

### 3.4 Acceptance criteria
- From a real phone, send a message to the sandbox number; within seconds an event with `source=whatsapp`
  appears for the right plant and the worker receives a reply.
- Ambiguous message → clarification question in WhatsApp → answer → same pipeline outcome as the web path.
- Unregistered number → refusal, no DB write. Bad signature → 403, no DB write. Duplicate delivery → one event.
- Worker token cannot call confirm/reject/import/recompute (403), verified by tests.
- If any of the above cannot be demonstrated end-to-end on the deployed URL, **the deck/report must call
  WhatsApp "roadmap", not "implemented".**

---

## 4. WS4 — React Native (Expo) mobile app  **[P1]**

**Finding (Copilot, verified):** the repo contains **no `mobile/` directory**, and `frontend-react/` is a
web app (browser `sessionStorage` token, same-origin `/api/v1`, no mobile base URL). So the React Native app
is either in a different folder/repo or does not exist yet. **Step 0 for the implementer: ask the owner where
the mobile code lives.** If it exists elsewhere, audit it against §4.1 and merge it under `mobile/` on the
v2 branch. If it does not exist, build it from scratch per the scope below (do not assume prior work).

Scope, per the original build prompt: Ingest, Review queue, Activities list, Audit (read-only). Reposition it
as the **worker/field companion** (capture + status) with an optional planner view of the review queue.

### 4.1 Known risks to check and cure
1. **Cleartext HTTP.** The deployed API is `http://`. iOS (App Transport Security) and Android 9+ block
   cleartext by default, so the app can fail on a device while working in a browser. **Cure:** serve the API
   over HTTPS (WS6) and point the app at it. Use a cleartext exception only for local dev, never for the
   submitted build.
2. **CORS is not the issue on native.** Native React Native `fetch` does not enforce browser CORS; CORS only
   matters if someone runs Expo **Web**. (An earlier note suggested CORS errors on Expo dev; that applies to
   Expo Web only.) Do not loosen backend CORS for the mobile app.
3. **Token handling.** Store the bearer token with `expo-secure-store`, not AsyncStorage/plain constants; do
   not commit tokens or `.env` with real values. Provide `.env.example`.
4. **API contract drift.** Confirm every endpoint the app calls exists with the same request/response shape
   (`/api/v1/reports`, `/review-queue`, `/events/{id}/candidates`, `/events/{id}/confirm|reject`,
   `/projects/{id}/activities`, `/audit`). Add a typed API client with one place for base URL/auth/error
   handling. Handle 401 (bad token), 503 (model/service down), network failure, and timeouts distinctly.
5. **Project context.** The app must let the user pick the active plant (WS2) and include `project_id` on
   every call.
6. **Distribution.** For judging, provide either an Expo Go QR / EAS internal build **or** a signed Android
   APK. Document exactly how a judge installs it. Run `npx expo-doctor` and `npx tsc --noEmit` clean.

### 4.2 Acceptance criteria
- On a **physical phone** (not just simulator), against the deployed HTTPS URL: submit a report and see the
  decision; open the review queue and confirm one item; see it in the audit list.
- Wrong token → clear "not authorised" message; server unreachable → clear offline message; no crashes.
- `expo-doctor` and TypeScript checks pass; README explains install + config in under 10 lines.

---

## 5. WS5 — Audit trail download (export)  **[P1, small]**

*(Interpreted as: an in-app download of the audit trail, plus this report being a downloadable file. If a
different meaning was intended, ask before building.)*

### 5.1 Current state
No export endpoint or download button exists (`GET /api/v1/audit` returns JSON only).

### 5.2 Changes
1. `GET /api/v1/audit/export?project_id=&format=csv|xlsx&from=&to=` (authenticated, project-scoped), with
   `Content-Disposition: attachment`. Columns: timestamp, event id, activity code, action, actor, source,
   before/after progress and status, score, margin, decision, evidence summary.
2. **Spreadsheet-injection safe**: any cell starting with `=`, `+`, `-`, `@` is prefixed with `'`.
3. UI: "Download CSV / Excel" buttons on the Audit view; mobile: share-sheet export.
4. The export respects the active plant and date filter; row cap with a clear message if exceeded.

### 5.3 Acceptance criteria
- Downloaded file opens in Excel/Sheets with correct columns and row count equal to the on-screen audit list.
- A crafted comment beginning with `=cmd` appears as inert text in the export (test).
- Unauthenticated request → 401.

---

## 6. WS6 — HTTPS and hardening (unblocks WS3 and WS4)  **[P0 for WS3/WS4]**

1. Put the deployment behind **HTTPS**: Elastic Beanstalk load balancer + ACM certificate + a domain/subdomain
   you control (or CloudFront in front). Redirect HTTP → HTTPS.
2. **Rotate the demo bearer token** and store it in EB environment properties, not in the repo/image.
3. Restrict CORS to the real HTTPS web origin (keep `*` out of production).
4. Basic rate limiting on ingest/webhook endpoints; request size limits are already set for import (10 MB).
5. Keep SQLite for the demo but set a persistent volume/backup note; document that multi-instance scaling
   requires a shared DB.
6. Remove/avoid logging secrets; confirm no tokens in git history (rotate if any were ever committed).

Acceptance: `curl -I https://…` returns 200/401 as expected; HTTP redirects; mobile app and (if built)
WhatsApp webhook work over HTTPS; old token no longer valid.

---

## 7. WS7 — Claims-vs-reality check for the deck and report  **[P1, ~1 hour]**

Before resubmitting, make every public claim true or relabel it "roadmap":
- Slide 6 says **"Offline / on-premise — no constant connectivity required"** and slide 3 lists
  **"PostgreSQL / SQLite"**: the deployed system is SQLite on a single AWS instance. Say what is true.
- Slide 2 says **"voice"** input and a **"Time Agent"**: verify voice works on the deployed HTTPS site
  (browser speech/mic permissions differ on HTTP vs HTTPS).
- **WhatsApp, mobile app, multi-plant onboarding**: mention as implemented only if the §3/§4/§2 acceptance
  criteria were demonstrated on the deployed system.
- Fill **Project Links** (slide 7), remove the duplicate Technical Approach slide, fix the clipped "2026"
  title, fill Team ID. Export to PDF and click every link; scan the QR code from a phone.
- Add a short "Worker → WhatsApp/App → ProgressSync → Planner" journey slide only if WS3/WS4 pass.

---

## 8. Known low-priority items (do only if time remains)
Mobile web layout clipping below ~390 px; 22 form fields without `id`/`name` (accessibility);
future-dated reports accepted without an upper bound; UNMATCHED path never exercised on the live
environment (do this one **now**: submit a report about a non-existent activity such as "valve ZZ999 done" and
confirm UNMATCHED, no schedule write, no one-click confirm).

---

## 9. Execution order (recommended)
| Phase | Work | Why this order |
|------:|------|----------------|
| 0 | Branch `v2-remediation`, second EB environment, baseline tests + benchmark green | Safe fallback |
| 1 | WS1 MiniLM diagnosis + cure + hardening | Core product claim (semantic matching) must be true |
| 2 | WS6 HTTPS + token rotation | Unblocks mobile + WhatsApp |
| 3 | WS5 audit export | Small, high visible value |
| 4 | WS2 dynamic plants | Biggest product-story upgrade; pure backend/UI, no external dependency |
| 5 | WS4 React Native (against HTTPS) | Needs Phase 2 |
| 6 | WS3 roles + WhatsApp (Twilio sandbox) | Highest risk; do last, cut if not fully working |
| 7 | WS7 deck/report alignment, final PDF | Only describe what is proven |

**Cut rule:** if a phase is not fully passing its acceptance criteria by the cutoff, drop it from the
submission and list it as roadmap. Never ship a half-working feature under the "implemented" label.

## 10. Release gates (all must pass before cutover / submission)
- [ ] Full pytest suite green; frozen benchmark: 0 silent errors, precision unchanged
- [ ] `frontend-react` build clean; `npm audit` no high/critical
- [ ] Live `/api/v1/ml/status` → semantic available; paraphrase test passes on the live URL
- [ ] All five SIH demo scenarios + UNMATCHED path re-run on the deployed **HTTPS** URL
- [ ] Two-plant isolation tests pass
- [ ] Audit export downloads correctly
- [ ] Mobile app verified on a physical device (if included)
- [ ] WhatsApp verified from a real phone end-to-end (if included), else labelled roadmap
- [ ] Demo DB reset; new token issued; old token dead
- [ ] Repo canonical URL decided; final code pushed; deploy matches the pushed commit
- [ ] PDF exported, all links and QR verified from a different device/network

## 11. Deliverables Claude Code must return
1. A short change log per WS (files touched, migrations, new endpoints).
2. Evidence for each acceptance criterion (real request/response or a description of what rendered).
3. Updated `README.md` and `docs/api.md` for the new endpoints, env vars, and deployment steps.
4. A list of anything cut or deferred, with the reason.
