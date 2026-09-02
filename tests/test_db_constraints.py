"""Schema invariants enforced by PostgreSQL itself (Day 1 tasks 7.5-7.9).

The offline model tests assert these against SQLAlchemy metadata; here the database does
the enforcing. Every test is marked ``db`` and rolls back through ``db_session``.
"""

import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ChildAllergy, ChildNote, ChildProfile, Feeding, GrowthMeasurement, User
from backend.models.enums import Allergen, FeedingType, NoteKind, Sex
from backend.schemas.child import ChildProfileWrite
from tests.conftest import make_user

pytestmark = pytest.mark.db


def profile(user: User, **overrides) -> ChildProfile:
    fields = {
        "user_id": user.id,
        "birth_date": dt.date(2026, 1, 10),
        "weight_kg": Decimal("8.5"),
        "sex": Sex.FEMALE,
    }
    fields.update(overrides)
    return ChildProfile(**fields)


class TestBirthDate:
    """child-profile spec: age is derived from a stored date of birth, in months."""

    def test_typed_age_rejected_before_the_database(self) -> None:
        """The write model takes a date of birth only; a typed age -- whole or fractional --
        is refused rather than converted."""
        for age in (8, 8.5):
            with pytest.raises(ValidationError):
                ChildProfileWrite.model_validate(
                    {"age_months": age, "weight_kg": 8.5, "sex": "female"}
                )

    async def test_round_trips_as_a_date(self, db_session: AsyncSession, user: User) -> None:
        child = profile(user, birth_date=dt.date(2026, 1, 31))
        db_session.add(child)
        await db_session.flush()
        await db_session.refresh(child, attribute_names=["birth_date"])
        assert child.birth_date == dt.date(2026, 1, 31)
        # Month-end birthday: 28 Feb is the clamped anniversary, so one completed month.
        assert child.age_months_on(dt.date(2026, 2, 27)) == 0
        assert child.age_months_on(dt.date(2026, 2, 28)) == 1
        assert child.age_months_on(dt.date(2026, 3, 31)) == 2


class TestAllergenVocabulary:
    """Hard rule 2: an off-vocabulary allergen cannot be stored."""

    async def test_off_vocabulary_string_rejected(self, db_session: AsyncSession, user: User):
        child = profile(user)
        db_session.add(child)
        await db_session.flush()
        db_session.add(ChildAllergy(child_profile_id=child.id, allergen="gluten"))
        with pytest.raises((DBAPIError, LookupError)):
            await db_session.flush()

    async def test_duplicate_allergen_violates_the_primary_key(
        self, db_session: AsyncSession, user: User
    ) -> None:
        child = profile(user)
        db_session.add(child)
        await db_session.flush()
        db_session.add(ChildAllergy(child_profile_id=child.id, allergen=Allergen.PEANUT))
        await db_session.flush()
        db_session.add(ChildAllergy(child_profile_id=child.id, allergen=Allergen.PEANUT))
        with pytest.raises(IntegrityError, match="pk_child_allergies"):
            await db_session.flush()

    async def test_allergies_round_trip_as_values(self, db_session: AsyncSession, user: User):
        child = profile(user)
        child.allergens = [Allergen.PEANUT, Allergen.MILK, Allergen.EGG]
        db_session.add(child)
        await db_session.flush()
        # Re-read from the database rather than trusting the identity map.
        await db_session.refresh(child, attribute_names=["allergies"])
        assert sorted(child.allergens) == [Allergen.EGG, Allergen.MILK, Allergen.PEANUT]


class TestEmailUniqueness:
    """user-account spec: email comparison ignores case."""

    async def test_case_variant_is_a_duplicate(self, db_session: AsyncSession) -> None:
        await make_user(db_session, "Parent@Example.com")
        db_session.add(User(email="parent@example.com", hashed_password="x"))
        with pytest.raises(IntegrityError, match="uq_users_email_lower"):
            await db_session.flush()

    async def test_original_casing_is_preserved(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session, "Parent@Example.com")
        assert (await db_session.get(User, user.id)).email == "Parent@Example.com"


class TestCascadeDeletion:
    """user-account spec: account deletion removes owned data."""

    async def test_deleting_a_user_removes_profiles_allergies_and_feedings(
        self, db_session: AsyncSession, user: User
    ) -> None:
        child = profile(user)
        child.allergens = [Allergen.SOY]
        db_session.add(child)
        await db_session.flush()
        db_session.add(
            Feeding(
                child_profile_id=child.id,
                fed_at=func.now(),
                feeding_type=FeedingType.BREASTMILK,
                quantity=None,
            )
        )
        db_session.add(
            GrowthMeasurement(
                child_profile_id=child.id,
                measured_on=dt.date(2026, 5, 10),
                weight_kg=Decimal("7.2"),
            )
        )
        db_session.add(
            ChildNote(child_profile_id=child.id, kind=NoteKind.DOCTOR, text="no honey", position=0)
        )
        await db_session.flush()

        await db_session.delete(user)
        await db_session.flush()

        for table in (ChildProfile, ChildAllergy, Feeding, GrowthMeasurement, ChildNote):
            count = await db_session.scalar(select(func.count()).select_from(table))
            assert count == 0, table.__tablename__


class TestWeightPrecision:
    """child-profile spec: weight is stored without loss of recorded precision."""

    @pytest.mark.parametrize("weight", ["8.4", "8.45", "60.00"])
    async def test_round_trips_exactly(self, db_session: AsyncSession, user: User, weight: str):
        child = profile(user, weight_kg=Decimal(weight))
        db_session.add(child)
        await db_session.flush()
        await db_session.refresh(child, attribute_names=["weight_kg"])
        assert child.weight_kg == Decimal(weight)

    async def test_zero_rejected(self, db_session: AsyncSession, user: User) -> None:
        db_session.add(profile(user, weight_kg=Decimal("0")))
        with pytest.raises(IntegrityError, match="weight_kg_positive"):
            await db_session.flush()


class TestChildNoteRules:
    async def test_blank_row_rejected(self, db_session: AsyncSession, user: User) -> None:
        child = profile(user)
        db_session.add(child)
        await db_session.flush()
        db_session.add(
            ChildNote(child_profile_id=child.id, kind=NoteKind.DOCTOR, text="   ", position=0)
        )
        with pytest.raises(IntegrityError, match="child_notes_text_not_blank"):
            await db_session.flush()

    async def test_rows_round_trip_in_order(self, db_session: AsyncSession, user: User) -> None:
        child = profile(user)
        child.notes = [
            ChildNote(kind=NoteKind.PREFERENCE, text="no pork", position=1),
            ChildNote(kind=NoteKind.DOCTOR, text="no honey", position=0),
        ]
        db_session.add(child)
        await db_session.flush()
        await db_session.refresh(child, attribute_names=["notes"])
        assert [(n.kind, n.text) for n in child.notes] == [
            (NoteKind.DOCTOR, "no honey"),
            (NoteKind.PREFERENCE, "no pork"),
        ]


class TestFeedingRules:
    async def test_quantity_required_unless_breastmilk(self, db_session: AsyncSession, user: User):
        child = profile(user)
        db_session.add(child)
        await db_session.flush()
        db_session.add(
            Feeding(child_profile_id=child.id, fed_at=func.now(), feeding_type=FeedingType.FORMULA)
        )
        with pytest.raises(IntegrityError, match="quantity_required_unless_breastmilk"):
            await db_session.flush()

    async def test_unknown_unit_rejected(self, db_session: AsyncSession, user: User) -> None:
        child = profile(user)
        db_session.add(child)
        await db_session.flush()
        db_session.add(
            Feeding(
                child_profile_id=child.id,
                fed_at=func.now(),
                feeding_type=FeedingType.FORMULA,
                quantity=Decimal("150"),
                unit="oz",
            )
        )
        with pytest.raises(IntegrityError, match="unit_known"):
            await db_session.flush()


class TestGrowthMeasurementRules:
    """growth-tracking spec: positive measurements, one per child per day."""

    async def _child(self, db_session: AsyncSession, user: User) -> ChildProfile:
        child = profile(user)
        db_session.add(child)
        await db_session.flush()
        return child

    async def test_zero_weight_rejected(self, db_session: AsyncSession, user: User) -> None:
        child = await self._child(db_session, user)
        db_session.add(
            GrowthMeasurement(
                child_profile_id=child.id, measured_on=dt.date(2026, 5, 10), weight_kg=Decimal("0")
            )
        )
        with pytest.raises(IntegrityError, match="growth_measurements_weight_kg_positive"):
            await db_session.flush()

    async def test_zero_height_rejected(self, db_session: AsyncSession, user: User) -> None:
        child = await self._child(db_session, user)
        db_session.add(
            GrowthMeasurement(
                child_profile_id=child.id,
                measured_on=dt.date(2026, 5, 10),
                weight_kg=Decimal("7.2"),
                height_cm=Decimal("0"),
            )
        )
        with pytest.raises(IntegrityError, match="growth_measurements_height_cm_positive"):
            await db_session.flush()

    async def test_one_measurement_per_day(self, db_session: AsyncSession, user: User) -> None:
        child = await self._child(db_session, user)
        for weight in ("7.2", "7.3"):
            db_session.add(
                GrowthMeasurement(
                    child_profile_id=child.id,
                    measured_on=dt.date(2026, 5, 10),
                    weight_kg=Decimal(weight),
                )
            )
        with pytest.raises(IntegrityError, match="uq_growth_measurements_child_day"):
            await db_session.flush()
