"""Food-table revisions: the food table moves into the database, seeded from the file.

Revision ID: d4a9b3c4e004
Revises: c3f8a2e2d003
Create Date: 2026-09-03 12:00:00

food-table-admin design Decisions 1 and 7. ``food_table_revisions`` holds one whole-table
JSONB snapshot per administrative write. Revision 1 is seeded here from
``nutrition-data/foods.yaml`` through the application's own loader -- a deliberate exception
to the initial migration's "no live imports" rule: the seed should be the file as validated
at the time this migration runs, and a fresh database with an invalid seed should fail here,
not at the first request. No enum types are touched. The downgrade drops the table; edits
made through the admin page since the seed are lost, and the file is served again.
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4a9b3c4e004"
down_revision: str | None = "c3f8a2e2d003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOODS_YAML = Path(__file__).resolve().parents[2] / "nutrition-data" / "foods.yaml"


def upgrade() -> None:
    revisions = op.create_table(
        "food_table_revisions",
        sa.Column("revision", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("table", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_food_table_revisions_revision_positive")),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_food_table_revisions_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("revision", name=op.f("pk_food_table_revisions")),
    )

    from backend.nutrition.foods import load_food_table

    table = load_food_table(FOODS_YAML)
    payload = table.table.model_dump(mode="json", exclude={"version"})
    op.bulk_insert(
        revisions,
        [
            {
                "revision": 1,
                "table": payload,
                "actor_user_id": None,
                "summary": f"Seeded from nutrition-data/foods.yaml {table.version}",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("food_table_revisions")
