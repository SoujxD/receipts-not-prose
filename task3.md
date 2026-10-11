# Task 3: Change history design (a proposal, not implemented)

> **This is a design only.** None of it exists in the code yet: there's no revision table,
> migration or viewer. The receipts in the chat UI are a different, lighter thing. They're tool
> results saved in a chat's conversation, and they only cover changes made through chat. This
> design would cover every change to an entity, however it was made.

## Goal

For a `FormSubmission` (and later other entities), answer: *which fields changed, from what, to
what, when, and through which path*, reliably, even after the row is deleted.

## Model: `entity_revision` (append-only)

| Column | Type | Purpose |
|---|---|---|
| `id` | `BIGINTEGER` PK (autoincrement) | Row identity only; never used for ordering per entity. |
| `entity_type` | `VARCHAR(64)` | e.g. `"form_submission"`. Names the table/model. |
| `entity_id` | `VARCHAR(64)` | Opaque ID of that entity (our IDs are `secrets.token_urlsafe` strings, not UUIDs). |
| `revision` | `INTEGER` | 1, 2, 3… per `(entity_type, entity_id)`. Defines order. |
| `operation` | `VARCHAR(16)` | `create` \| `update` \| `delete`. |
| `occurred_at` | `DATETIME` (UTC) | When the change was committed. |
| `schema_version` | `SMALLINT` | Version of the snapshot shape for this `entity_type`. |
| `before` | `JSON` NULL | Full snapshot before the change (`NULL` for `create`). |
| `after` | `JSON` NULL | Full snapshot after the change (`NULL` for `delete`). |
| `changed_fields` | `JSON` | `{field: {"from": x, "to": y}}`, derived from `before`/`after`. |
| `actor_type` | `VARCHAR(16)` | `user` \| `assistant_tool` \| `system` \| `migration`. |
| `actor_id` | `VARCHAR(64)` NULL | **Authenticated** principal, set by the server. Never taken from model output. |
| `source` | `VARCHAR(32)` | `rest_api`, `chat_tool`, `admin_script`… |
| `request_id` | `VARCHAR(64)` NULL | Correlates with logs / one HTTP request. |
| `tool_call_id` | `VARCHAR(64)` NULL | Links a chat-tool change to its transcript entry. |
| `chat_id` | `VARCHAR(32)` NULL | Context only. Not a foreign key. |

Constraints and indexes:

- `UNIQUE (entity_type, entity_id, revision)` makes ordering unambiguous and rejects duplicate revision numbers. It also serves the main read: "history of this entity, in order".
- An index on `occurred_at` if we need "recent changes across everything".
- No indexes on JSON properties. The requirement is "what changed and when", not "filter by field value".

The entity table gains one column, `version INTEGER NOT NULL DEFAULT 0` (the current revision number).

### Example: a phone change, then status cleared to null

```json
{"entity_type": "form_submission", "entity_id": "Xk3…", "revision": 3, "operation": "update",
 "occurred_at": "2026-10-10T17:02:11Z", "schema_version": 1,
 "before": {"name": "Ada Lovelace", "email": "ada@example.com", "phone_number": "+44 20 7946 0958", "status": 2},
 "after":  {"name": "Ada Lovelace", "email": "ada@example.com", "phone_number": "+44 20 7946 0000", "status": null},
 "changed_fields": {"phone_number": {"from": "+44 20 7946 0958", "to": "+44 20 7946 0000"},
                    "status": {"from": 2, "to": null}},
 "actor_type": "assistant_tool", "actor_id": "user_123", "source": "chat_tool", "tool_call_id": "call_abc"}
```

`"status": null` in `after` and `{"from": 2, "to": null}` record that the status was **cleared**.
That is not the same as status being absent from `changed_fields`, which means it didn't change.

## Why small snapshots + derived diff

- **Diff-only** rows are compact, but to see the state at revision N you must replay revisions 1…N. One lost or bad row breaks every later reconstruction.
- **Full event sourcing**, where the event log is the source of truth, would change how every read in the app works. That's too much for a 7-field record.
- **Snapshots + diff**: each row stands alone (`after` *is* the state at that revision), and `changed_fields` answers "what changed" without a client-side diff. A form is a few hundred bytes, so the storage cost is trivial. `changed_fields` is computed from `before`/`after` by one shared function, so it cannot disagree with them.

## Lifecycle

- **Create** → revision 1, `before = NULL`, `after = snapshot`. This establishes the baseline. Existing rows would be backfilled with a revision 1, `source = "migration"`.
- **Update** → `revision = version + 1`. `changed_fields` lists only fields whose value actually differs.
- **Delete** → a final `delete` revision with `before = last snapshot`, `after = NULL`: a tombstone. The form row disappears; its history stays.

Missing vs null vs unchanged follows the PATCH contract already implemented in `forms.update_form`:

- A key omitted from the request is not compared and not recorded.
- An explicit `null` (status only) is recorded as a change to `null`.
- A value equal to the current one is not a change.

**A no-op update (no changed fields) writes no revision and does not bump `version`.**

## One write path, one transaction

All mutations already go through `backend/forms.py` (`create_form`, `update_form`, `delete_form`), used by both the REST routes and the chat tools. Implementation would add a `record_revision(...)` call inside those functions. The entity write and the revision insert would happen **in the same transaction, with one commit**. That means replacing today's per-call commits in `crud.py` with flush-then-commit at the service layer. Either both rows exist or neither does.

## Concurrency

`MAX(revision) + 1` is not safe: two concurrent writers can read the same max. Instead, use optimistic concurrency on the entity row:

```sql
UPDATE form_submission SET ..., version = version + 1
WHERE id = :id AND version = :expected_version;
```

- If 0 rows are affected, someone else changed it first. Return `409 Conflict`, or re-read and retry if the change is still valid.
- The new `version` becomes the revision number. The unique constraint is a second guard against duplicates.
- Clients can send the expected version (e.g. `If-Match`), so a stale UI cannot silently overwrite a newer change.

For deletes, the tombstone's revision comes from the same version check. Inserting the very first revision is safe because the entity ID is fresh.

## Polymorphic reference tradeoff

`(entity_type, entity_id)` cannot be a real foreign key to every table, so the database won't check referential integrity. That is intentional here: history **must not** cascade away when the entity is deleted. (Today `Chat.form_submissions` uses `cascade="all, delete"`; history must stay out of that cascade.) Integrity is enforced in the shared write path instead. A per-type history table is the alternative: you get real foreign keys, but lose the single reusable model.

## Schema changes, retention and access

- `schema_version` lets readers interpret old snapshots after fields are renamed or added. Old rows are never rewritten. Readers upgrade them when reading.
- Snapshots hold contact data (name, email, phone), so history must follow the same access rules as the forms, or stricter ones. Deletion/erasure requests need a defined policy, e.g. redact PII in snapshots while keeping the structure of revisions.
- Append-only is an application convention. It does not make the data tamper-proof or legally compliant. Stronger guarantees would need DB permissions that block UPDATE/DELETE on the table, and possibly hash-chaining rows. Both are future decisions.
