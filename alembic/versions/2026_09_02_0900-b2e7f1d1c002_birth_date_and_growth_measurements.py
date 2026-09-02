"""Date of birth replaces the typed age; growth measurements table.

Revision ID: b2e7f1d1c002
Revises: a1d6f0c0b001
Create Date: 2026-09-02 09:00:00

growth-tracking design Decisions 1, 4 and 8. ``birth_date`` is backfilled as the youngest
date consistent with "``age_in_months`` completed months when the profile was created":
``created_at`` (as a UTC date) minus that many calendar months. PostgreSQL clamps a
month-end date the way ``backend.nutrition.age.completed_months`` does, so the two agree.
``created_at`` rather than ``now()`` keeps the backfill deterministic on any dump. The
downgrade recomputes ``age_in_months`` from the same two columns, clamped to 0-60 so the
restored CHECK can be re-added, and drops the measurements table. No enum types change.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2e7f1d1c002"
down_revision: str | None = "a1d6f0c0b001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("child_profiles", sa.Column("birth_date", sa.Date(), nullable=True))
    op.execute(
        "UPDATE child_profiles SET birth_date = "
        "((created_at AT TIME ZONE 'UTC')::date - make_interval(months => age_in_months))::date"
    )
    op.alter_column("child_profiles", "birth_date", nullable=False)
    op.drop_constraint(
        op.f("ck_child_profiles_age_in_months_range"), "child_profiles", type_="check"
    )
    op.drop_column("child_profiles", "age_in_months")

    op.create_table(
        "growth_measurements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_profile_id", sa.Uuid(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("height_cm", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "weight_kg > 0", name=op.f("ck_growth_measurements_weight_kg_positive")
        ),
        sa.CheckConstraint(
            "height_cm IS NULL OR height_cm > 0",
            name=op.f("ck_growth_measurements_height_cm_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["child_profile_id"],
            ["child_profiles.id"],
            name=op.f("fk_growth_measurements_child_profile_id_child_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_growth_measurements")),
        sa.UniqueConstraint(
            "child_profile_id", "measured_on", name="uq_growth_measurements_child_day"
        ),
    )


def downgrade() -> None:
    op.drop_table("growth_measurements")

    op.add_column(
        "child_profiles", sa.Column("age_in_months", sa.SmallInteger(), nullable=True)
    )
    op.execute(
        "UPDATE child_profiles SET age_in_months = LEAST(60, GREATEST(0, "
        "date_part('year', age((created_at AT TIME ZONE 'UTC')::date, birth_date)) * 12 + "
        "date_part('month', age((created_at AT TIME ZONE 'UTC')::date, birth_date))))::smallint"
    )
    op.alter_column("child_profiles", "age_in_months", nullable=False)
    op.create_check_constraint(
        op.f("ck_child_profiles_age_in_months_range"),
        "child_profiles",
        "age_in_months >= 0 AND age_in_months <= 60",
    )
    op.drop_column("child_profiles", "birth_date")
