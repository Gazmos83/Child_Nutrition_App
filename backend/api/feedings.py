"""``POST /api/feedings`` -- validate and price one feeding entry (feeding-log spec).

Stateless today: the same ``log_feeding`` the router's tool uses, returning the normalised
entry with its identifier and table-derived nutrients for the browser to keep. Day 6 adds
authentication and the row write here, and nowhere else.
"""

from fastapi import APIRouter, HTTPException, status

from backend.nutrition.feeding import FeedingEntryError
from backend.nutrition.foods import FoodNotFoundError
from backend.schemas.tools import FeedingEntry, LoggedFeeding
from backend.tools.feeding_log import log_feeding

router = APIRouter(tags=["feedings"])


@router.post(
    "/feedings",
    response_model=LoggedFeeding,
    summary="Log one feed",
    responses={
        422: {"description": "The entry contradicts the food table (unknown food, wrong unit)."}
    },
)
def create_feeding(entry: FeedingEntry) -> LoggedFeeding:
    """Return the entry normalised against the food table, with an id and its nutrients.

    Nothing is stored and no identity is taken; the client keeps the returned entry.
    """
    try:
        return log_feeding(entry)
    except FoodNotFoundError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown food id {exc.food_id!r}: choose a food from /api/foods",
        ) from exc
    except FeedingEntryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
