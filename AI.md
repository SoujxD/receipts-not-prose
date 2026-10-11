# AI usage

I used AI tools a lot on this take-home, so here's an honest account of where, why, and how I made sure the result is something I understand and stand behind.

## Where I used AI

**ChatGPT, before writing any code.** I used it to:
- break down the assignment and the starter repo;
- read up on Aurelian's public product pages (AVA, CORA) and the product engineer job posting, so I could pick a direction that fits;
- turn my plan into a detailed implementation brief: priorities, the REST and status contracts, the failure cases worth testing, and the core idea of showing receipts instead of trusting the assistant's prose.

**Claude Code (Anthropic), for implementation.** I gave it that brief and worked with it in this repo. It wrote or modified:
- **Backend:** `schemas.py`, `forms.py` (new), `agent.py` (new), `main.py`, small additions to `crud.py`, `DATABASE_URL` support in `database.py` and `alembic/env.py`, plus `.env.example` and `requirements-dev.txt`.
- **Tests:** everything in `backend/tests/`.
- **Frontend:** the chat page, the home page, the layout and styles, `utils/fetcher.ts`, `utils/types.ts`, and the new `components/` folder.
- **Docs:** the reviewer guide at the top of `README.md`, `task3.md`, and drafts of this file.

## Why I used it this way

The suggested time was 1 to 4 hours. I wanted to spend my own attention on the decisions rather than on typing. The decisions I cared most about:
- what "trustworthy" should mean for this feature;
- keeping an unset status (`null`) separate from TO DO;
- treating "field left out" and "field set to null" differently in PATCH;
- what should happen when a save succeeds but the model fails right after;
- what to leave out: no auth and no full audit system.

AI helped me apply those decisions consistently across the backend, tests, UI and docs.

## How the work was checked

I instructed Claude Code to run the checks below during development. Afterwards I re-ran and verified the key ones myself (see the next section).
- The backend test suite: 71 tests, run against a freshly migrated temporary SQLite database, with a fake model client so nothing calls OpenAI.
- A quick sanity check that the tests actually catch bugs. We planted two realistic bugs, saw the right tests fail, then restored the code:
  - using `exclude_none` instead of `exclude_unset` in PATCH;
  - dropping the `chat_id` condition from the form lookup.
- `alembic upgrade head` on a fresh database.
- `npx tsc --noEmit`, `npm run lint` and `npm run build`.

**Live model check.** I asked Claude Code to run the walkthrough twice against the real `gpt-4o-mini`, using synthetic data. The key stayed in a local, git-ignored `backend/.env`.
- **The first run caught a real problem.** With two forms both named "Ada Lovelace", the request "Delete Ada's form." deleted one of them without asking which.
- **The fix:** a clearer system prompt, plus a server-side check that refuses to update or delete a form that shares its name with another, unless the user names something that identifies it (email, phone or form ID). A regression test covers it.
- **The second run:** the assistant asked which Ada I meant, then deleted the right one.

## What I verified myself

- **Tests.** I ran the backend suite on my machine (`python -m pytest -q`) and got 71 passed.
- **Browser walkthrough.** On a fresh database, with the real model, I clicked through the whole flow:
  - the assistant asking for missing details;
  - saving two forms;
  - updating one through chat and checking the receipt showed exactly what changed;
  - filtering by status and clearing a status back to Unset;
  - reloading the page to confirm everything persisted;
  - the same-name clarification followed by the correct delete;
  - the optional status dropdown;
  - copying a form ID.

  Everything behaved as described in the README.
- **REST API.** I tried the endpoints through `/docs`:
  - `?status=null` returned only Unset forms, and `?status=4` was rejected with 422;
  - PATCH rejected `true`, `0` and `chat_id` with 422;
  - a phone-only PATCH left the other fields alone;
  - `"status": null` cleared the status.
- **Code.** I read through `schemas.py`, `forms.py`, `agent.py`, `main.py`, `ActionReceipt.tsx`, the chat page's `send()` and `task3.md`, so I can explain and defend the decisions in them.

I'm not making any claims here about time saved, test coverage percentages, or production readiness.
