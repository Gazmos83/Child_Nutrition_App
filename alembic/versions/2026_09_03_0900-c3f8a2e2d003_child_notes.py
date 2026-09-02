"""Doctor's-note and preference rows replace the profile's single note.

Revision ID: c3f8a2e2d003
Revises: b2e7f1d1c002
Create Date: 2026-09-03 09:00:00

child-notes-restrictions design Decisions 1 and 2. A new ``note_kind`` enum and a
``child_notes`` table, one row per instruction. Every existing note was written as a
doctor's note, so the backfill turns each of its non-blank lines into one ``doctor`` row,
dated with the note's own recorded-at. The downgrade joins the doctor rows back into the
column with newlines (earliest recorded-at kept); preference rows and blank lines are lost
on downgrade, which is acceptable for a database with no production data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3f8a2e2d003"
down_revision: str | None = "b2e7f1d1c002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spelled out, not imported: a migration is a snapshot (see the initial revision).
note_kind = postgresql.ENUM("doctor", "preference", name="note_kind", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    note_kind.create(bind, checkfirst=True)

    op.create_table(
        "child_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_profile_id", sa.Uuid(), nullable=False),
        sa.Column("kind", note_kind, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("btrim(text) <> ''", name=op.f("ck_child_notes_text_not_blank")),
        sa.CheckConstraint("position >= 0", name=op.f("ck_child_notes_position_non_negative")),
        sa.ForeignKeyConstraint(
            ["child_profile_id"],
            ["child_profiles.id"],
            name=op.f("fk_child_notes_child_profile_id_child_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_child_notes")),
    )
    op.create_index(
        op.f("ix_child_notes_child_profile_id"), "child_notes", ["child_profile_id"], unique=False
    )

    # One doctor row per non-blank line of the old note, in line order, dated as the note.
    op.execute(
        """
        INSERT INTO child_notes (id, child_profile_id, kind, text, position, created_at)
        SELECT gen_random_uuid(), l.id, 'doctor', l.line,
               (row_number() OVER (PARTITION BY l.id ORDER BY l.n) - 1)::smallint,
               l.recorded
        FROM (
            SELECT p.id, p.doctors_note_recorded_at AS recorded, btrim(s.line) AS line, s.n
            FROM child_profiles p
            CROSS JOIN LATERAL regexp_split_to_table(p.doctors_note, E'\\r?\\n')
                 WITH ORDINALITY AS s(line, n)
            WHERE p.doctors_note IS NOT NULL AND btrim(s.line) <> ''
        ) l
        """
    )

    op.drop_constraint(
        op.f("ck_child_profiles_doctors_note_paired_with_timestamp"), "child_profiles", type_="check"
    )
    op.drop_column("child_profiles", "doctors_note_recorded_at")
    op.drop_column("child_profiles", "doctors_note")


def downgrade() -> None:
    op.add_column("child_profiles", sa.Column("doctors_note", sa.Text(), nullable=True))
    op.add_column(
        "child_profiles",
        sa.Column("doctors_note_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE child_profiles p
        SET doctors_note = n.joined, doctors_note_recorded_at = n.recorded
        FROM (
            SELECT child_profile_id,
                   string_agg(text, E'\\n' ORDER BY position, created_at) AS joined,
                   min(created_at) AS recorded
            FROM child_notes
            WHERE kind = 'doctor'
            GROUP BY child_profile_id
        ) n
        WHERE n.child_profile_id = p.id
        """
    )
    op.create_check_constraint(
        op.f("ck_child_profiles_doctors_note_paired_with_timestamp"),
        "child_profiles",
        "(doctors_note IS NULL) = (doctors_note_recorded_at IS NULL)",
    )
    op.drop_index(op.f("ix_child_notes_child_profile_id"), table_name="child_notes")
    op.drop_table("child_notes")
    note_kind.drop(op.get_bind(), checkfirst=True)
