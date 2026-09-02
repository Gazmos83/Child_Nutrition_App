"""ORM schema guarantees that hold without a database (tasks 5.1-5.6).

These assert against SQLAlchemy metadata and in-memory instances. The same invariants are
re-verified against real PostgreSQL in the group 7 integration tests, where the database
does the enforcing -- these catch a broken model definition before a migration is ever run.
"""

import datetime as dt
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint, DateTime, UniqueConstraint

from backend.db.base import Base
from backend.models import (
    ChildAllergy,
    ChildNote,
    ChildProfile,
    FoodTableRevision,
    GrowthMeasurement,
    User,
)
from backend.models.enums import Allergen, DietPreference, NoteKind, Sex
from backend.nutrition.age import today


class TestUUIDPrimaryKey:
    """Task 5.1 / design.md Decision 3."""

    def test_ids_are_time_ordered_and_not_sequential(self) -> None:
        first, second = uuid.uuid7(), uuid.uuid7()
        assert second > first, "UUIDv7 must be time-ordered"
        # Not merely incremented: the random tail must make the gap unguessable.
        assert int(second) - int(first) > 1

    def test_id_default_generates_a_v7_uuid(self) -> None:
        # SQLAlchemy wraps the callable to accept an execution context, so assert on
        # behaviour rather than on the identity of the wrapped function.
        # ChildAllergy is excluded: it has a composite primary key, not a UUID id.
        for model in (User, ChildProfile, GrowthMeasurement):
            column_default = model.__table__.c.id.default
            assert column_default is not None, model.__name__
            generated = column_default.arg(None)
            assert isinstance(generated, uuid.UUID)
            assert generated.version == 7, model.__name__

    def test_generated_ids_are_version_7(self) -> None:
        assert uuid.uuid7().version == 7


class TestUserTable:
    """Task 5.2 / design.md Decision 4."""

    def test_case_insensitive_email_index_exists(self) -> None:
        index_names = {index.name for index in User.__table__.indexes}
        assert "uq_users_email_lower" in index_names

    def test_email_index_is_unique_and_functional(self) -> None:
        index = next(i for i in User.__table__.indexes if i.name == "uq_users_email_lower")
        assert index.unique is True
        # The index is over lower(email), not the raw column.
        assert "lower" in str(index.expressions[0]).lower()

    def test_required_columns_present_and_not_nullable(self) -> None:
        columns = User.__table__.c
        for name in ("email", "hashed_password", "is_active", "created_at"):
            assert name in columns, name
            assert columns[name].nullable is False, name

    def test_password_is_never_stored_plaintext_named(self) -> None:
        # Guard against a future rename that drops the "hashed" signal.
        assert "password" not in User.__table__.c
        assert "hashed_password" in User.__table__.c


class TestAgeInMonths:
    """Task 5.3 / hard rule 1 / design.md Decision 7; growth-tracking design Decision 1."""

    def test_no_age_years_column_anywhere(self) -> None:
        for table in Base.metadata.sorted_tables:
            for column in table.c:
                assert "age_years" not in column.name, f"{table.name}.{column.name}"
                assert "age_in_years" not in column.name, f"{table.name}.{column.name}"

    def test_no_age_years_attribute_on_the_model(self) -> None:
        assert not hasattr(ChildProfile, "age_years")
        assert not hasattr(ChildProfile, "age_in_years")

    def test_birth_date_is_a_date_column_not_null(self) -> None:
        column = ChildProfile.__table__.c.birth_date
        assert column.type.python_type is dt.date
        assert column.nullable is False

    def test_no_typed_age_column_and_no_age_check_remains(self) -> None:
        assert "age_in_months" not in ChildProfile.__table__.c
        assert not any("age" in name for name in _check_constraints(ChildProfile))

    def test_age_is_derived_in_completed_months(self) -> None:
        profile = _build_profile(birth_date=dt.date(2026, 1, 10))
        assert profile.age_months_on(dt.date(2026, 5, 9)) == 3
        assert profile.age_months_on(dt.date(2026, 5, 10)) == 4
        # Born "tomorrow" in the parent's time zone: clamped, never negative.
        assert _build_profile(birth_date=today() + dt.timedelta(days=1)).age_months == 0


class TestGrowthMeasurement:
    """growth-tracking design Decision 4."""

    def test_columns_are_fixed_point_and_a_calendar_date(self) -> None:
        columns = GrowthMeasurement.__table__.c
        assert (columns.weight_kg.type.precision, columns.weight_kg.type.scale) == (5, 2)
        assert columns.weight_kg.nullable is False
        assert (columns.height_cm.type.precision, columns.height_cm.type.scale) == (4, 1)
        assert columns.height_cm.nullable is True
        assert columns.measured_on.type.python_type is dt.date
        assert columns.measured_on.nullable is False

    def test_positivity_checks_exist(self) -> None:
        checks = _check_constraints(GrowthMeasurement)
        assert "ck_growth_measurements_weight_kg_positive" in checks
        assert "ck_growth_measurements_height_cm_positive" in checks

    def test_one_measurement_per_child_per_day(self) -> None:
        unique = [
            c for c in GrowthMeasurement.__table__.constraints if isinstance(c, UniqueConstraint)
        ]
        assert [c.name for c in unique] == ["uq_growth_measurements_child_day"]
        assert [col.name for col in unique[0].columns] == ["child_profile_id", "measured_on"]

    def test_foreign_key_cascades_on_delete(self) -> None:
        fk = next(iter(GrowthMeasurement.__table__.c.child_profile_id.foreign_keys))
        assert fk.ondelete == "CASCADE"


class TestWeight:
    """design.md Decision 6."""

    def test_weight_is_fixed_point_not_float(self) -> None:
        column = ChildProfile.__table__.c.weight_kg
        assert column.type.python_type is Decimal
        assert (column.type.precision, column.type.scale) == (5, 2)

    def test_weight_positive_check_exists(self) -> None:
        assert "ck_child_profiles_weight_kg_positive" in _check_constraints(ChildProfile)


class TestChildNote:
    """child-notes-restrictions design Decision 1: rows with a kind replace the note column."""

    def test_profile_has_no_note_columns(self) -> None:
        columns = ChildProfile.__table__.c
        assert "doctors_note" not in columns and "doctors_note_recorded_at" not in columns
        assert not any("doctors_note" in name for name in _check_constraints(ChildProfile))

    def test_row_columns_and_checks(self) -> None:
        columns = ChildNote.__table__.c
        assert columns.kind.type.name == "note_kind"
        assert set(columns.kind.type.enums) == {"doctor", "preference"}
        assert columns.text.nullable is False and columns.position.nullable is False
        checks = _check_constraints(ChildNote)
        assert "ck_child_notes_text_not_blank" in checks
        assert "ck_child_notes_position_non_negative" in checks

    def test_foreign_key_cascades_and_rows_load_eagerly_in_order(self) -> None:
        fk = next(iter(ChildNote.__table__.c.child_profile_id.foreign_keys))
        assert fk.ondelete == "CASCADE"
        relationship = ChildProfile.__mapper__.relationships["notes"]
        assert relationship.lazy == "selectin"
        assert relationship.cascade.delete_orphan

    def test_profile_is_valid_with_no_rows_and_rows_carry_provenance(self) -> None:
        profile = _build_profile()
        assert profile.notes == []
        recorded = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
        row = ChildNote(kind=NoteKind.DOCTOR, text="Iron supplementation advised.", position=0)
        row.created_at = recorded
        profile.notes.append(row)
        assert profile.notes[0].kind is NoteKind.DOCTOR
        assert profile.notes[0].created_at == recorded


class TestTimestampsAreTimezoneAware:
    """design.md Decision 10, enforced across every model."""

    def test_all_datetime_columns_are_timestamptz(self) -> None:
        for table in Base.metadata.sorted_tables:
            for column in table.c:
                if isinstance(column.type, DateTime):
                    assert column.type.timezone is True, f"{table.name}.{column.name}"


class TestAllergyJoinTable:
    """Task 5.5 / design.md Decision 8."""

    def test_composite_primary_key_has_exactly_two_columns(self) -> None:
        pk_columns = list(ChildAllergy.__table__.primary_key.columns)
        assert len(pk_columns) == 2
        assert {c.name for c in pk_columns} == {"child_profile_id", "allergen"}

    def test_no_redundant_unique_constraint(self) -> None:
        # The composite PK already covers this tuple; a second index would be dead weight.
        from sqlalchemy import UniqueConstraint

        unique = [c for c in ChildAllergy.__table__.constraints if isinstance(c, UniqueConstraint)]
        assert unique == []

    def test_foreign_key_cascades_on_delete(self) -> None:
        fk = next(iter(ChildAllergy.__table__.c.child_profile_id.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_profile_user_fk_cascades_on_delete(self) -> None:
        fk = next(iter(ChildProfile.__table__.c.user_id.foreign_keys))
        assert fk.ondelete == "CASCADE"


class TestAllergyRelationship:
    """Task 5.6."""

    def test_three_allergens_read_back_as_three_distinct_values(self) -> None:
        profile = _build_profile()
        profile.allergens.extend([Allergen.PEANUT, Allergen.MILK, Allergen.SESAME])

        assert len(profile.allergies) == 3
        # Distinct enum members, not one delimited string.
        assert set(profile.allergens) == {Allergen.PEANUT, Allergen.MILK, Allergen.SESAME}
        assert all(isinstance(a, Allergen) for a in profile.allergens)

    def test_no_allergies_is_an_empty_set_not_a_sentinel(self) -> None:
        profile = _build_profile()
        assert profile.allergies == []
        assert list(profile.allergens) == []

    def test_allergen_values_are_not_concatenated(self) -> None:
        profile = _build_profile()
        profile.allergens.append(Allergen.TREE_NUT)
        assert profile.allergies[0].allergen is Allergen.TREE_NUT


class TestDietPreferenceDefault:
    def test_column_default_is_the_vocabulary_default(self) -> None:
        column = ChildProfile.__table__.c.diet_preference
        assert column.default.arg is DietPreference.default()
        assert column.nullable is False

    def test_server_default_matches_python_default(self) -> None:
        column = ChildProfile.__table__.c.diet_preference
        assert column.server_default.arg == DietPreference.default().value


class TestNativeEnumLabels:
    """design.md Decision 2: DB labels must be the lowercase enum *values*."""

    @pytest.mark.parametrize(
        ("table_name", "column_name", "expected"),
        [
            ("child_profiles", "sex", {"male", "female"}),
            (
                "child_profiles",
                "diet_preference",
                {"omnivore", "vegetarian", "pescatarian", "vegan"},
            ),
            ("child_allergies", "allergen", {a.value for a in Allergen}),
        ],
    )
    def test_enum_labels_are_values(
        self, table_name: str, column_name: str, expected: set[str]
    ) -> None:
        column = Base.metadata.tables[table_name].c[column_name]
        assert set(column.type.enums) == expected
        assert column.type.native_enum is True


def _check_constraints(model: type) -> dict[str, str]:
    return {
        c.name: str(c.sqltext)
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name
    }


def _build_profile(**overrides) -> ChildProfile:
    defaults = {
        "user_id": uuid.uuid7(),
        "birth_date": dt.date(2026, 1, 10),
        "weight_kg": Decimal("8.40"),
        "sex": Sex.FEMALE,
        "diet_preference": DietPreference.OMNIVORE,
    }
    return ChildProfile(**(defaults | overrides))


class TestFoodTableRevision:
    """food-table-admin design Decision 1: whole-table snapshots, one per write."""

    def test_revision_is_the_assigned_primary_key(self) -> None:
        column = FoodTableRevision.__table__.c.revision
        assert column.primary_key and column.autoincrement is False
        assert "ck_food_table_revisions_revision_positive" in _check_constraints(FoodTableRevision)

    def test_snapshot_and_actor(self) -> None:
        columns = FoodTableRevision.__table__.c
        assert columns.table.type.__class__.__name__ == "JSONB" and columns.table.nullable is False
        fk = next(iter(columns.actor_user_id.foreign_keys))
        assert fk.ondelete == "SET NULL" and columns.actor_user_id.nullable is True
        assert columns.summary.nullable is False
