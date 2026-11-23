"""Let Pro and Ultra open monthly tutor reports and CSV export.

Revision ID: 0031_tutor_reports
Revises: 0030_topic_homework
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_tutor_reports"
down_revision: str | None = "0030_topic_homework"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the tutor_reports module to Pro and Ultra (agency)."""
    op.execute(
        """
        UPDATE plans
        SET modules = modules || '["tutor_reports"]'::jsonb
        WHERE code IN ('pro', 'agency')
          AND NOT (modules @> '["tutor_reports"]'::jsonb)
        """
    )


def downgrade() -> None:
    """Remove the tutor_reports module from Pro and Ultra."""
    op.execute(
        """
        UPDATE plans
        SET modules = COALESCE(
            (
                SELECT jsonb_agg(elem)
                FROM jsonb_array_elements(modules) AS elem
                WHERE elem <> '"tutor_reports"'::jsonb
            ),
            '[]'::jsonb
        )
        WHERE code IN ('pro', 'agency')
        """
    )
