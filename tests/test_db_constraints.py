"""Schema invariants enforced by PostgreSQL itself (Day 1 tasks 7.5-7.9).

The offline model tests assert these against SQLAlchemy metadata; here the database does
the enforcing. Every test is marked ``db`` and rolls back through ``db_session``.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ChildAllergy, ChildProfile, Feeding, User
from backend.models.enums import Allergen, FeedingType, Sex
from backend.schemas.child import ChildProfileWrite
from tests.conftest import make_user

pytestmark = pytest.mark.db


def profile(user: User, **overrides) -> ChildProfile:
    fields = {
        "user_id": user.id,
        "age_in_months": 8,
        "weight_kg": Decimal("8.5"),
        "sex": Sex.FEMALE,
    }
    fields.update(overrides)
    return ChildProfile(**fields)


class TestAgeInMonths:
    """child-profile spec: age is represented in months."""

    @pytest.mark.parametrize("age", [-1, 61])
    async def test_out_of_range_rejected(self, db_session: AsyncSession, user: User, age: int):
        db_session.add(profile(user, age_in_months=age))
        with pytest.raises(IntegrityError, match="age_in_months_range"):
            await db_session.flush()

    def test_fraction_rejected_before_the_database(self) -> None:
        """PostgreSQL would *round* 8.5 into a smallint, not refuse it (Day 1 task 7.5 assumed
        otherwise); the write model is where a fractional month is rejected."""
        with pytest.raises(ValidationError):
            ChildProfileWrite.model_validate({"age_months": 8.5, "weight_kg": 8.5, "sex": "female"})

    @pytest.mark.parametrize("age", [0, 8, 60])
    async def test_in_range_accepted(self, db_session: AsyncSession, user: User, age: int):
        child = profile(user, age_in_months=age)
        db_session.add(child)
        await db_session.flush()
        assert (await db_session.get(ChildProfile, child.id)).age_in_months == age


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
        await db_session.flush()

        await db_session.delete(user)
        await db_session.flush()

        for table in (ChildProfile, ChildAllergy, Feeding):
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


class TestDoctorsNotePairing:
    async def test_note_without_timestamp_rejected(self, db_session: AsyncSession, user: User):
        db_session.add(profile(user, doctors_note="limit to 650 kcal"))
        with pytest.raises(IntegrityError, match="doctors_note_paired_with_timestamp"):
            await db_session.flush()


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
