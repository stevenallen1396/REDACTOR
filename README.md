# The REDACTOR

A tool that:
1. Takes a batch of documents — PDFs, `.eml` / `.msg` emails, or a folder mixing both — and produces the same batch back with all personal information permanently redacted. Emails are converted to PDF automatically before redaction, so you can just drop a folder in and get redacted PDFs out.
2. Lets you list **exemptions**: terms (staff names, your own company name, etc.) that should never be redacted even though they look like PII.

Runs entirely locally by default: no documents, emails, or text are ever sent anywhere, no API key, no subscription. It can optionally be deployed online for a small team to share (see **Hosting it online** below) — that's a deliberate, explicit opt-in, not the default.

## Run it locally

```
./run.sh
```

First run installs everything into a local virtual environment (a few minutes, one-time). Every run after that starts in a couple of seconds. It opens automatically at http://127.0.0.1:8420 — reachable only from this machine.

## Using it

Drop PDFs, `.eml`/`.msg` files, or a whole folder mixing both onto the page (or use "choose files" / "choose a folder"). List any exemptions, one per line, then click **Redact & download ZIP**. Any email files in the batch are converted to PDF first; every PDF — original or converted — is then redacted, and the whole batch comes back as one ZIP, mirroring the folder structure you dropped in.

## How redaction works

- Text is extracted from each PDF page and scanned with [Microsoft Presidio](https://microsoft.github.io/presidio/) (local NER + pattern matching) for names, email addresses, phone numbers, addresses, IBANs, credit card numbers, plus custom UK-specific detectors for postcodes, National Insurance numbers, and UK mobile numbers.
- Matches are **physically removed** from the PDF via PyMuPDF's redaction annotations (`apply_redactions`) — this strips the underlying content, not just draws a black box on top, so it can't be recovered by copy-paste or re-extracting the text.
- Anything you list in the **Exemptions** box (one term per line) is left untouched, even if it looks like PII.
- By default, generic dates (`DATE_TIME`) and URLs aren't redacted, since Presidio flags every date-shaped string with no way to tell an invoice date from a birth date — for ordinary business documents that would over-redact far more than intended. If your documents contain sensitive dates (e.g. dates of birth) you want caught automatically, remove `"DATE_TIME"` from `EXCLUDED_ENTITIES` in `backend/app/redact.py`.
- Outlook/Word HTML emails often encode bullet points as private-use Unicode characters tied to the Wingdings/Symbol font. `email_to_pdf.py` detects and remaps the common ones so they render as real bullets instead of a "missing glyph" box — see `_fix_symbol_font_glyphs`.

**Always spot-check the output before sending redacted documents onward.** Automatic PII detection is not perfect — review a sample from each batch.

## Limits

- Max 100 files per batch, max 30MB per file (see `MAX_FILES` / `MAX_FILE_SIZE` in `backend/app/main.py` — just constants, change them if you need more).
- Processing is synchronous (roughly 1–3 seconds per page), so very large batches will take a few minutes.

## Project structure

```
backend/app/main.py            FastAPI routes + static frontend mount
backend/app/auth.py            HTTP Basic Auth middleware (only active when hosted, see below)
backend/app/redact.py          PDF redaction pipeline (Presidio + PyMuPDF)
backend/app/pii_recognizers.py Custom UK PII pattern recognizers
backend/app/email_to_pdf.py    .eml / .msg -> PDF conversion (WeasyPrint)
frontend/                      Plain HTML/CSS/JS UI, no build step
Dockerfile, render.yaml        For hosting online (optional, see below)
```

## Hosting it online

By default the app only listens on `127.0.0.1`, so nothing but your own machine can reach it. If you want a few named colleagues to be able to use it from their own browsers instead of each running it locally, it can be deployed to [Render](https://render.com)'s free tier as a Docker container. Worth understanding before doing this: your documents would then be processed on Render's server rather than your own machine — still under your control (nobody but your logged-in users can reach it), but a real difference from the fully local setup above.

**What's already in place for this:**
- `Dockerfile` — builds a container with WeasyPrint's system libraries and a smaller spaCy model (`en_core_web_sm` instead of the `en_core_web_lg` used locally) sized to fit a free tier's ~512MB RAM limit. Tested locally under a 512MB cap: ~190MB used at idle plus a full redaction run.
- `backend/app/auth.py` — HTTP Basic Auth for every request (API and page alike), gated entirely by the `REDACTOR_USERS` environment variable. Unset (the local default), nothing changes. Set it, and every request needs matching credentials.
- `render.yaml` — a Render "blueprint" so the service config is defined in the repo rather than clicked together by hand.

**Steps to deploy:**
1. Push this repo to GitHub (a `origin` remote is already configured — `git push -u origin main` once you've committed).
2. Sign up at [render.com](https://render.com) (free, no card required for the free tier as of writing).
3. New → Blueprint → connect this GitHub repo. Render will read `render.yaml` and set up the service automatically.
4. In the service's Environment settings, set `REDACTOR_USERS` to a comma-separated `username:password` list, e.g. `steven:correcthorse,jane:anotherpassword`. Use real, distinct passwords — this is HTTP Basic Auth, so it's only as strong as what you put here (traffic is protected by Render's automatic HTTPS, but there's no lockout/rate-limiting, so avoid weak or shared passwords).
5. Deploy. Render gives you a free `https://the-redactor-xxxx.onrender.com` URL automatically.

**Trade-offs of the free tier, worth knowing going in:**
- It spins down after 15 minutes idle; the next request wakes it up with a ~30–60 second cold start.
- It uses `en_core_web_sm` rather than `en_core_web_lg` to fit the RAM budget — noticeably lower accuracy for name/location detection than the local setup. Spot-checking output matters even more here.
- No per-user activity log or rate-limiting beyond what's built in — fine for a small trusted team, not a substitute for a real access-control system if that's ever needed.
