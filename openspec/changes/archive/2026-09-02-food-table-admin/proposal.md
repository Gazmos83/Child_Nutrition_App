## Why

The food table has 57 hand-typed entries in a committed YAML file and no way to grow it
without a code change and a deploy. Parents ask about foods the table does not know, and the
planner composes from the same short list every day. The operator wants to add foods
themselves — one at a time and in bulk from a file — without touching the repository. The
hard rules do not forbid this, but they set the terms: the safety flags the infant-safety
filter relies on (hard rule 4) and the source behind every number (hard rule 5) must be
entered explicitly per food; every write must be validated whole (hard rule 7); every plan's
audit record must keep naming a table version that can be reproduced (hard rule 8); and the
table is global, so writing it needs a role that ordinary accounts do not have (hard rule 9).

**Scope: [Stretch]. Post-MVP follow-on (Day 11 in the project's numbering).** No model call,
no new npm or Python dependency.

## What Changes

- **The table moves into PostgreSQL as whole-table revisions.** A `food_table_revisions`
  row holds the complete validated table as JSONB; every write appends the next revision.
  The committed `foods.yaml` seeds revision 1 at migration time and remains the fallback
  when no database table has been loaded (unit tests, a dev instance without a database).
  The served version becomes `db-<revision>`, so a plan's `food_table_version` names a row
  that reproduces exactly what the planner saw.
- **Administrators are designated by configuration.** `ADMIN_EMAILS` (comma-separated)
  names the accounts allowed to write the table; `/api/auth/me` reports `is_admin` so the
  UI can show the entry point. Non-administrators get 403 on every admin route.
- **Create, edit, deactivate — never delete.** `POST`, `PUT /{food_id}`, `POST
  /{food_id}/deactivate` and `/activate` under `/api/admin/foods`. Each write requires the
  four safety fields explicitly (no defaults), a `source`, and passes the existing whole-table
  validation; solids must be 6 months or older and only breast milk and formula may be
  `milk_feed` (those two are protected from deactivation). An inactive food leaves the
  picker, the planner, and name lookup, but is still priced for feeds already logged with it.
- **Bulk import from a file.** `POST /api/admin/foods/import` takes the file's text as JSON
  (`yaml` or `csv`, ≤ 1 MiB), validates the merged table whole, reports created / updated /
  unchanged rows and per-row errors naming `row`, `id`, `field`, and writes nothing when any
  row fails; `dry_run` previews. A JSON body keeps the API's JSON-only CSRF posture and avoids
  a multipart dependency.
- **An admin page.** `/admin/foods`: the table with active/inactive state, a create/edit form
  whose safety questions are yes/no with nothing preselected, deactivate/activate, and an
  import panel with a dry-run preview. Non-administrators see a refusal, not data.

## Capabilities

### New Capabilities

- `food-table-admin`: administrator role by configuration; create, edit, deactivate with
  complete safety metadata and a source; bulk import validated whole; every write is a new
  table revision named in plan audits; inactive foods hidden from picker, planner, and lookup
  but still priced for stored feeds; protected milk feeds; refusals for non-admins.

### Modified Capabilities

- `food-composition-data`: the table is stored in the application database as whole-table
  revisions seeded from the committed file and validated whole on every write; the served
  version names the revision; a deactivated entry is not resolvable by name but remains
  retrievable by identifier.
- `authentication`: the signed-in account read carries whether the account is an
  administrator.
- `observability`: every table write emits one structured record with the revision and a
  summary (no email); a plan audit's table version names a stored revision.
- `chat-ui`: an administrator sees an entry point to the food-table page; a
  non-administrator opening it sees a refusal.

## Impact

- **Database**: new table `food_table_revisions` (no enum types); migration seeds revision 1
  from `nutrition-data/foods.yaml` via the existing loader; downgrade drops the table.
- **Backend**: `backend/nutrition/foods.py` (`is_active`, min-age rule, active/all split,
  module-level cache with `set_food_table`, `table_from_revision`), new
  `backend/nutrition/food_admin.py` (pure import/merge/validate logic), new
  `backend/db/food_table.py` (load latest, insert revision), new
  `backend/models/food_table_revision.py`, `backend/core/config.py` (`admin_emails`,
  `rate_limit_admin_per_minute`), `backend/api/deps.py` (`require_admin`),
  `backend/api/auth.py` + `schemas/auth.py` (`is_admin`), new `backend/api/admin_foods.py`,
  `backend/schemas/admin.py`, `backend/api/rate_limit.py` (`admin` bucket), `backend/main.py`
  lifespan load, `tests/test_app.py` route surface.
- **Frontend**: `app/admin/foods/page.tsx`, `components/admin/{food-table,food-form,
  import-panel}.tsx`, `hooks/use-admin-foods.ts`, `lib/admin-food-form.ts`, `lib/enums.ts`
  (`FoodCategory`), `api-types.ts`, `copy.ts` + snapshot, admin link in `chat-page.tsx`,
  account-scoped cache removal in `use-session.ts`/`providers.tsx`.
- **Config/deploy**: `.env.example`, `render.yaml` (`ADMIN_EMAILS`, `sync: false`); `prod`
  refuses to start if the database table cannot be loaded; a dev instance falls back to the
  file with a warning.
- **API contract**: additive — five admin routes, `is_admin` on the account read.
- **Security**: admin routes behind `require_admin`; owner-scoped data untouched; nothing new
  reaches the language model.

## Non-goals

- USDA FoodData Central prefill or any external nutrient API. [Stretch]
- Deleting a food, or a UI for granting the admin role.
- A per-food history view (the revision table holds it; no page reads it yet). [Stretch]
- Multi-instance cache invalidation — the service runs as one instance by design.
- Editing `foods.yaml` after the seed — it documents the seed and the fallback, nothing more.
