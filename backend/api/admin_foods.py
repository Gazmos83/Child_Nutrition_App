"""``/api/admin/foods`` -- administrators grow and correct the food table (food-table-admin
spec).

Every route runs behind ``AdminUser`` (``backend/api/deps.py``): the table is global, not
user-scoped, and only accounts listed in ``ADMIN_EMAILS`` may write it. Every write loads the
latest revision, applies the change through ``backend/nutrition/food_admin`` (which validates
the whole table exactly as the committed file is validated), appends the next revision, and
swaps the served table -- one instance, so the in-process swap is exact.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import AdminUser, DbSession
from backend.api.rate_limit import rate_limited
from backend.db.food_table import RevisionConflict, insert_revision, load_latest
from backend.models import User
from backend.nutrition.food_admin import (
    AdminRuleError,
    FoodWrite,
    apply_write,
    parse_import,
    plan_import,
    set_active,
    snapshot,
)
from backend.nutrition.foods import (
    FoodNotFoundError,
    FoodTable,
    LoadedFoodTable,
    get_food_table,
    set_food_table,
    table_from_revision,
)
from backend.schemas.admin import (
    FoodImportRequest,
    FoodImportResult,
    FoodTableAdminResponse,
    FoodWriteResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/foods", tags=["admin"])

NO_SUCH_FOOD_DETAIL = "No such food"
REVISION_CONFLICT_DETAIL = "The food table changed while you were editing; reload and try again"
WRITE_LIMITED = [Depends(rate_limited("admin"))]


async def _current(db: DbSession) -> tuple[int, LoadedFoodTable]:
    """The latest stored revision, or the served (committed) table as revision 0."""
    latest = await load_latest(db)
    if latest is None:
        return 0, get_food_table()
    return latest.revision, table_from_revision(latest.revision, latest.table)


async def _write(
    db: DbSession, user: User, table: FoodTable, summary: str
) -> tuple[int, LoadedFoodTable]:
    payload = snapshot(table)
    try:
        revision = await insert_revision(db, payload, user.id, summary)
    except RevisionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=REVISION_CONFLICT_DETAIL) from exc
    served = table_from_revision(revision, payload)
    set_food_table(served)
    return revision, served


def _rule_error(exc: AdminRuleError) -> HTTPException:
    code = status.HTTP_409_CONFLICT if exc.conflict else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(code, detail=str(exc))


@router.get("", response_model=FoodTableAdminResponse, summary="Every food, inactive included")
async def list_all_foods(user: AdminUser, db: DbSession) -> FoodTableAdminResponse:
    revision, table = await _current(db)
    return FoodTableAdminResponse(
        version=table.version, revision=revision, source=table.table.source, foods=table.all_foods
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=FoodWriteResponse,
    summary="Create a food",
    dependencies=WRITE_LIMITED,
    responses={409: {"description": "A food with that id already exists."}},
)
async def create_food(body: FoodWrite, user: AdminUser, db: DbSession) -> FoodWriteResponse:
    _, current = await _current(db)
    try:
        table = apply_write(current.table, body, create=True)
    except AdminRuleError as exc:
        raise _rule_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    revision, served = await _write(db, user, table, f"Created {body.id}")
    return FoodWriteResponse(food=served.get(body.id), version=served.version, revision=revision)


@router.put(
    "/{food_id}",
    response_model=FoodWriteResponse,
    summary="Replace a food's entry",
    dependencies=WRITE_LIMITED,
    responses={404: {"description": "No such food."}, 409: {"description": "Protected food."}},
)
async def replace_food(
    food_id: str, body: FoodWrite, user: AdminUser, db: DbSession
) -> FoodWriteResponse:
    if body.id != food_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="id in the body must match the path"
        )
    _, current = await _current(db)
    try:
        table = apply_write(current.table, body, create=False)
    except FoodNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_FOOD_DETAIL) from exc
    except AdminRuleError as exc:
        raise _rule_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    revision, served = await _write(db, user, table, f"Edited {food_id}")
    return FoodWriteResponse(food=served.get(food_id), version=served.version, revision=revision)


async def _set_active(food_id: str, active: bool, user: User, db: DbSession) -> FoodWriteResponse:
    revision, current = await _current(db)
    try:
        table, changed = set_active(current.table, food_id, active)
    except FoodNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_SUCH_FOOD_DETAIL) from exc
    except AdminRuleError as exc:
        raise _rule_error(exc) from exc
    if changed:
        verb = "Deactivated" if not active else "Reactivated"
        revision, current = await _write(db, user, table, f"{verb} {food_id}")
    return FoodWriteResponse(food=current.get(food_id), version=current.version, revision=revision)


@router.post(
    "/{food_id}/deactivate",
    response_model=FoodWriteResponse,
    summary="Hide a food from the picker, plans, and lookup (never deletes)",
    dependencies=WRITE_LIMITED,
    responses={404: {"description": "No such food."}, 409: {"description": "Protected food."}},
)
async def deactivate_food(food_id: str, user: AdminUser, db: DbSession) -> FoodWriteResponse:
    return await _set_active(food_id, False, user, db)


@router.post(
    "/{food_id}/activate",
    response_model=FoodWriteResponse,
    summary="Offer a food again",
    dependencies=WRITE_LIMITED,
    responses={404: {"description": "No such food."}},
)
async def activate_food(food_id: str, user: AdminUser, db: DbSession) -> FoodWriteResponse:
    return await _set_active(food_id, True, user, db)


@router.post(
    "/import",
    response_model=FoodImportResult,
    summary="Import foods from a YAML or CSV file; all or nothing",
    dependencies=WRITE_LIMITED,
    responses={422: {"description": "The file could not be read at all."}},
)
async def import_foods(body: FoodImportRequest, user: AdminUser, db: DbSession) -> FoodImportResult:
    """Validate the merged table whole. Any failing row means nothing is written and every
    failing row is named; a dry run reports the same without writing."""
    try:
        rows, file_source = parse_import(body.format, body.content)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    revision, current = await _current(db)
    plan = plan_import(current.table, rows, body.mode, file_source)
    applied = False
    version = current.version
    if plan.table is not None and plan.changes_anything and not body.dry_run:
        summary = f"Import: {len(plan.created)} created, {len(plan.updated)} updated"
        revision, served = await _write(db, user, plan.table, summary)
        version, applied = served.version, True
    return FoodImportResult(
        applied=applied,
        created=plan.created,
        updated=plan.updated,
        unchanged=plan.unchanged,
        errors=plan.errors,
        version=version,
        revision=revision,
    )
