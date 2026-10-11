# Reviewer guide

Hi Trevor, thanks for taking the time to look at this. The original assignment text is kept unchanged at the bottom of this file.

**The idea in one line:** the UI separates *what the assistant said* from *what the app actually did*.

Whenever a form is saved, updated or deleted through chat, the conversation shows a small **receipt**:
- It is built from the result the backend records *after* the database write finishes, never from the model's wording.
- An update receipt lists only the fields that really changed, old → new.
- A failed action looks clearly different ("Action failed … Nothing was changed").
- The panel of saved forms on the right is always re-read from the database.

## Running it

You'll need Python 3.10 to 3.12 (I used 3.11) and a recent Node/npm (I used Node 24 and npm 11).

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt  # requirements.txt plus pytest
cp .env.example .env                 # then paste the provided key into OPENAI_API_KEY
alembic upgrade head
uvicorn main:app --reload            # API docs at http://localhost:8000/docs

# Frontend (in a second terminal)
cd frontend
npm ci
npm run dev                          # http://localhost:3000
```

I moved the API key out of `main.py` and into `backend/.env`, so it never ends up in source control.

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_API_KEY` | none | Only needed for chatting (`PUT /chat/{id}`). Without it, chat returns a clear 503, but the REST endpoints, migrations and tests all still work. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Lets you swap the model. |
| `DATABASE_URL` | `sqlite+aiosqlite:///./dev.db` | Shared by the app and Alembic, which makes it easy to point at a throwaway database. |
| `NEXT_PUBLIC_API_URL` (frontend) | `http://localhost:8000` | Where the frontend finds the backend. |

**Tests:** `cd backend && python -m pytest -q`. They need no key and never call OpenAI.

## API

| Endpoint | What it does |
|---|---|
| `GET /chat/{chat_id}/forms` | Every form in the chat, oldest first (ties broken by ID). No pagination. Optional `?status=1`, `2`, `3` or `null`. |
| `PATCH /chat/{chat_id}/forms/{form_id}` | Updates any of `name`, `email`, `phone_number`, `status`. Anything you leave out stays as it is. |
| `DELETE /chat/{chat_id}/forms/{form_id}` | Returns `204` with no body. |
| `PUT /chat/{chat_id}` | The existing chat endpoint. The assistant can now submit, list, update and delete forms. |

An unknown chat returns `404`. A form that exists but belongs to a different chat also returns `404`, so other chats' forms can't be probed. A real chat with no matching forms returns `[]`.

**Status values:** `null` means **Unset** (the default for new forms), `1` is TO DO, `2` is IN PROGRESS, `3` is COMPLETED.
- **Request bodies:** only `null`, `1`, `2` or `3` are accepted. Things like `0`, `4`, `"1"`, `true`, `2.0` or `1.5` get a 422. I used `StrictInt` for this, because Python quietly treats `True` as `1`.
- **PATCH:** leaving `status` out keeps it as it is; sending `"status": null` clears it.
- **Filtering:** `GET ?status=null` returns the Unset forms. Anything that isn't a valid status gets a 422.

```bash
curl -X PATCH localhost:8000/chat/$CHAT/forms/$FORM -H 'content-type: application/json' -d '{"phone_number": "+1 415 555 0199", "status": 2}'
curl -X PATCH localhost:8000/chat/$CHAT/forms/$FORM -H 'content-type: application/json' -d '{"status": null}'   # clear the status
curl "localhost:8000/chat/$CHAT/forms?status=null"
curl -i -X DELETE localhost:8000/chat/$CHAT/forms/$FORM   # 204
```

**More PATCH rules:**
- Name, email and phone can't be blank or `null` if you send them.
- `id`, `chat_id`, `created_at` and unknown fields are rejected with a 422.
- An empty body, or values identical to what's saved, does nothing and returns the current record.

## Where to find things

| Task | Files |
|---|---|
| 1: save forms from chat and show them | `backend/agent.py` (`submit_interest_form`), `backend/forms.py` (`create_form`), `frontend/app/[chatId]/page.tsx`, `frontend/components/FormsPanel.tsx` |
| 2: update and delete through chat, plus the REST API | `backend/agent.py` (the list, update and delete tools, the loop and the fallback), `backend/forms.py` (validation and chat scoping **shared** by REST and the tools), `backend/schemas.py` (status and PATCH rules), `backend/main.py` (routes), `backend/crud.py` (chat-scoped lookup and full, ordered listing) |
| Receipts in the UI | `frontend/components/ActionReceipt.tsx`, `frontend/components/Conversation.tsx` |
| 3: change history design | `task3.md` (a design only; nothing is implemented) |
| Tests | `backend/tests/test_forms_api.py`, `backend/tests/test_chat_tools.py` |
| AI usage | `AI.md` |

## How a chat turn works, and what happens when things go wrong

**Tools are defined once** in `agent.TOOLS`, and only those can run.
- The model never chooses which chat it's working in; that always comes from the URL.
- Tool arguments go through the same validation as the REST API.
- If the model calls an unknown tool, sends broken JSON, uses invalid values, or points at a form that doesn't exist (or belongs to another chat), it gets back `{"ok": false, ...}` and nothing changes.

**Same-name check.** If two forms in a chat share a name, the server won't update or delete either one unless the user's message identifies which one (by email, phone or form ID). The chat shows a "Needs clarification" receipt instead.
- I added this after a live run. With two "Ada Lovelace" forms, *"Delete Ada's form."* made the model delete one of them without asking.

**Up to 4 model rounds per message**, so "look up the forms, then update one, then reply" works.
- Every tool call in a response is handled, in order, before the model continues.
- On the last round the model is asked for text only. If it still asks for tools, those calls are skipped and the app adds its own short note. No tool call is ever left without a result.

**Each save commits on its own.** A message that triggers several actions is not all-or-nothing.
- Earlier successes stay saved and are reported that way. A database error rolls back only that one action and shows up as `write_failed`.
- I never hold a database transaction open while waiting on the model.

**When the save works but the model fails right after.** This is the case I cared about most (`test_write_then_model_failure_keeps_record_and_records_honest_fallback`).
- The form stays saved, and its receipt stays in the conversation.
- The app adds its own plain message, shown as "Application notice", listing what was actually done.
- The request still returns normally, so the UI refreshes and you can see the receipt.
- Nothing gets run twice.
- If the model fails *before* anything happened, you get a 503, nothing is saved, and your typed message stays in the box so you can retry.

**Conversation history can't be rewritten from the browser.** The frontend still sends the full message list, as the starter did. The server only accepts it if it's exactly the saved conversation plus one new user message.
- A fake or edited assistant/tool message, or an out-of-date copy of the chat, gets a `409`.
- If the last message isn't a user message, that's a `422`.
- Creating a chat only accepts user messages.
- If a send fails or the outcome is unclear, the UI reloads the chat from the server before letting you retry. It never re-sends on its own.

## Assumptions (also noted in code comments)

- New forms start as Unset (`null`), which I treat as different from TO DO.
- Two submissions with the same details are two separate forms. I deliberately don't merge people.
- **Phone numbers:** the check is loose so international formats work: an optional `+`, then digits, spaces, `()`, `.` or `-`, with 7 to 15 digits in total. Numbers are stored exactly as entered.
- **Emails:** checked with `email_validator`, without a DNS lookup.
- The chat list still shows 10 chats, but now it's the 10 most recent (the starter's 10 weren't in any particular order).
- I didn't add a REST endpoint for creating forms, since forms come from chat and the README didn't ask for one.

## A three-minute walkthrough

Please use made-up contact details.

1. **Save two forms.**
   - Create a chat and say: *"Submit an interest form for Ada Lovelace, ada@example.com, +44 20 7946 0958"*.
   - Then add *Grace Hopper, grace@example.com, (555) 010-0199*.
   - You'll see two **Saved** receipts and two Unset cards.
2. **Update one through chat.**
   - Say: *"Change Grace's phone to +1 212 555 0100 and mark her in progress."*
   - The **Updated** receipt shows only the phone change and `Unset → IN PROGRESS`, and Grace's card updates to match.
3. **Filter, clear, reload.**
   - Click the **IN PROGRESS** filter. A note explains that other statuses are hidden.
   - Then say *"Clear Grace's status"* (or use the dropdown on her card). Grace drops out of that filtered view.
   - Switch to **Unset** and reload the page: everything is still there.
4. **Delete.**
   - Say *"Delete Ada's form."* You'll see a **Deleted** receipt and the card disappears.
   - To see the clarification step, first add a second Ada Lovelace with a different email. The assistant asks which one you mean, and the server won't guess even if the model tries to.
5. **The test that matters most.** Have a look at `test_write_then_model_failure_keeps_record_and_records_honest_fallback` in `backend/tests/test_chat_tools.py`.
   - This is where a chat app is most likely to mislead someone: the data changed, but without care the conversation could suggest nothing happened, and a retry could create a duplicate.

## What I checked

Checked on Windows 11 with Python 3.11 and Node 24.14.1:

| Check | Result |
|---|---|
| Backend tests (`python -m pytest -q`) | **71 passed** |
| Do the tests catch real bugs? (planted `exclude_none` in PATCH, then an unscoped form lookup) | The right tests failed each time; code restored afterwards |
| `alembic upgrade head` on a fresh database | Worked (`chat` and `form_submission` tables created) |
| `npx tsc --noEmit`, `npm run lint`, `npm run build` | All clean |
| Live walkthrough with the real `gpt-4o-mini` (synthetic data) | Run twice, details below |

**What the live model actually did:**
- It asked for missing details instead of making them up. For "Submit a form for Alan Turing" it asked for an email and phone.
- It saved Ada and Grace. For Grace's change it looked up the forms first, then updated her. The receipt showed exactly `phone_number: (555) 010-0199 → +1 212 555 0100` and `status: null → 2`.
- "Clear Grace's status" recorded `status: 2 → null`, and the `?status=2` and `?status=null` filters returned the right forms.
- **The first run found a real bug.** With two Ada Lovelace forms, "Delete Ada's form." deleted the newer one without asking. I fixed it with a clearer prompt and the server-side same-name check, plus a regression test (`test_same_name_target_requires_user_to_identify_it`).
- **The second run, after the fix:** the assistant asked *"Which one … ada@example.com or ada.l@example.com?"* and deleted the right form once the email was given.
  - In that run the prompt alone was enough, so the server check wasn't needed live. It's covered by the test.
- Model responses vary from run to run, so treat these as two real observations, not a guarantee.

**Checked by hand, and what's still open:**
- I clicked through the whole walkthrough myself in the browser, with the real model and a fresh database. Everything behaved as described, including persistence after reload and the same-name clarification. There are no automated browser tests in the repo.
- The "save worked, model failed" path is covered by the automated test only.
- `npm ci` reports audit warnings for the starter's pinned packages (for example Next 14.2.1). I left the versions alone on purpose.

## Known limitations (left out on purpose)

- **No login or permissions.** Anyone with a chat ID can read and change that chat. Chat scoping prevents mix-ups between chats, not deliberate misuse.
- **No protection against simultaneous edits.**
  - If two messages are sent to the same chat at the same moment, both can pass the history check, and the later one wins. A version number on each chat with a conditional update would fix this.
  - Form edits are also last write wins. `task3.md` describes how a version check would prevent that.
- **Not exactly-once.** The send button lock, the history check and reload-before-retry make failures recoverable, but they don't guarantee each action runs exactly once.
  - There's still a tiny window where the server could crash after saving a form but before recording its receipt in the chat.
  - The fix would be saving both in one transaction, or tracking each tool call ID so it can never apply twice.
- **The prompt helps, the server enforces.** The prompt asks the assistant to clarify when a request is ambiguous and to treat saved data as data, not instructions. The server checks still apply regardless.
  - The same-name check is a heuristic. It catches identical names, not every possible kind of ambiguity.
  - The model can never pick the chat, and every change is scoped by both chat ID and form ID.
- **Status is validated in the app**, not by a database constraint. That avoided an extra migration.
- **Optional extra:** the status dropdown on each form card goes a little beyond what the README asked for. It uses the same PATCH endpoint and is the only editing in the UI.

---

# Aurelian Take Home Assessment

## AI Usage

Since we cannot enforce a no AI policy for a take-home, you are allowed to use AI tools on this assessment. HOWEVER, please disclose any usage of AI tools in a file called AI.md and explain where you chose to use AI.

## Expectations

Your priority is to complete as much of the tasks as possible while maintaining a high bar for quality. If you find the requirements or specifications unclear at any point, leave comments in your code about the assumptions you made.

## Overview

We have provided you with a basic prototype of an AI chat application. The application has the ability to create chats and chat back and forth with the user.

Right now, the agent is extremely basic, pretty much just a vanilla version of ChatGPT with one additional function - the ability to collect interest forms. Your tasks will revolve around fleshing out this ability by saving interest forms to the database, and creating APIs and UIs to get and edit these interest forms.

## Tips

### Backend

Database tables are modeled in models.py - each class represents a table.

For APIs, see the endpoints in main.py. You can also visit http://localhost:8000/docs after running the backend server for simple documentation of each API endpoint. By looking at this documentation and the existing endpoints, you should be able to figure out how the API works. You can also look at the FastAPI documentation on the web for additional help.

There are also prebuilt CRUD functions for all database models already in crud.py. The best way to understand how to use these functions is to probably look at the existing POST /chat and PUT /chat/{chat_id} routes.

### Frontend

The frontend does require some knowledge of React but shouldn't require much knowledge of NextJS, if any. All you should need to know is that the different pages of the app can be found under the "app" folder. "page.tsx" generally represents the code for that page. Subfolders map to subroutes, so app/[chatId]/page.tsx would be the code for /[chatId] where chat ID is the ID of a given chat. Similarly, app/page.tsx is the code for /.

Again, we strongly recommend looking at and copying patterns from the existing code to make your job easier. Many common patterns such as getting data or sending POST requests may already have similar implementations. Remember these tasks are meant to be representative of working as a full stack engineer in an existing code base, so we encourage you to complete them as you would your normal work.

If you are completely unfamiliar with React, you can write the needed components in the framework of your choice as long as you let us know what framework you used and where to find your code. However, we would prefer you use React if at all possible.

## Getting Setup

Before doing anything else, paste the API key you were provided into backend/main.py where it says "YOUR_KEY_HERE"

### Backend/Database

```bash
cd backend

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

alembic upgrade head
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend

npm i

npm run dev
```

## Task 1 - Collect Structured Interest Form

The AI agent has a tool to collect an interest form. If a user requests to submit an interest form, the agent will ask for the required information, and then use the tool. Right now, the tool doesnt actually do anything. It just returns success.

Your task is to update the "update_chat" function in main.py so that the tool actually does something. Specifically, we want the tool to use the collected information to create a FormSubmission row in the database for each collected interest form. A database model and basic CRUD operations have already been provided for FormSubmissions for you to use.

To save you some time, you may find the capabilities section of the OpenAI docs to be helpful in understanding what the tool call schema looks like: https://platform.openai.com/docs/guides/function-calling?api-mode=chat

After you are able to successfully create FormSubmissions, update the UI and API to display all interest forms submitted during a particular chat in the chat UI. If I open a chat, I want to still see the chat window with all the messages, as well as a list of forms that were submitted as part of that particular chat. It is your discretion how to design the API and UI to accomodate this. For the sake of time, don't worry about how pretty your UI is - as long as it displays the data in a useful way, it's fine.

## Task 2 - Add additional functionality to the chat bot and API

We want to allow users to additionally update their form submissions and delete their form submissions via the chat interface. Augment the chat endpoint with additional logic to support this.

We will eventually want to be able to update the form submissions via the UI as well. Flesh out the REST API for working with FormSubmissions. Include at least the following endpoints and requirements:

1. Update a form submission. Should be able to update name, email, phone number, and status. Add a way to validate the status field. It should be either None, 1, 2, or 3. 1 = "TO DO", 2 = "IN PROGRESS", 3 = "COMPLETED"
2. Get all form submissions for a specific chat. Should be able to filter by status
3. Delete a form submission.

## Task 3 - Change History Design

We want to be able to track the full revision history of a Form Submission and all changes made after each update. Design a data model that would allow us to do this. Consider that in the future we may want to track the revision history of other things using this same model. The ability to filter by certain properties is not as important here. We just want to be able to determine what fields changed, what changed about them, and when they changed. No need to write code for this portion. Just include the details of your model and thought process in a file called task3.md
