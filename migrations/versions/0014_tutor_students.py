"""Tutor cabinet students: paid, owing, or inactive.

Revision ID: 0014_tutor_students
Revises: 0013_lookup_indexes
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_tutor_students"
down_revision: str | None = "0013_lookup_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE tutor_students (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER NOT NULL,
        name VARCHAR(80) NOT NULL,
        phone VARCHAR(20),
        status VARCHAR(16) NOT NULL,
        amount_uzs INTEGER NOT NULL DEFAULT 0,
        note VARCHAR(300),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE tutor_students
        ADD CONSTRAINT fk_tutor_students_owner_id_users
        FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE CASCADE
    """,
    """
    ALTER TABLE tutor_students
        ADD CONSTRAINT ck_tutor_students_status
        CHECK (status IN ('paid', 'debtor', 'inactive'))
    """,
    """
    ALTER TABLE tutor_students
        ADD CONSTRAINT ck_tutor_students_amount
        CHECK (amount_uzs >= 0 AND amount_uzs <= 1000000000)
    """,
    "CREATE INDEX ix_tutor_students_owner_id ON tutor_students (owner_id)",
)

_DOWNGRADE: tuple[str, ...] = ("DROP TABLE tutor_students",)


def upgrade() -> None:
    """Create the tutor student table."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Drop the tutor student table."""
    for statement in _DOWNGRADE:
        op.execute(statement)
