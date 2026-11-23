"""Course fees: monthly bills and lesson packages.

Revision ID: 0028_course_fees
Revises: 0027_attendance
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_course_fees"
down_revision: str | None = "0027_attendance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE: tuple[str, ...] = (
    """
    ALTER TABLE tutor_groups
        ADD COLUMN fee_mode VARCHAR(16) NOT NULL DEFAULT 'none',
        ADD COLUMN fee_uzs INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN package_lessons SMALLINT,
        ADD COLUMN billing_day SMALLINT,
        ADD COLUMN due_days SMALLINT NOT NULL DEFAULT 5
    """,
    """
    ALTER TABLE tutor_groups
        ADD CONSTRAINT ck_tutor_groups_fee_mode
            CHECK (fee_mode IN ('none', 'monthly', 'package')),
        ADD CONSTRAINT ck_tutor_groups_fee_uzs
            CHECK (fee_uzs >= 0 AND fee_uzs <= 1000000000),
        ADD CONSTRAINT ck_tutor_groups_package
            CHECK (package_lessons IS NULL OR (package_lessons >= 1 AND package_lessons <= 100)),
        ADD CONSTRAINT ck_tutor_groups_billing_day
            CHECK (billing_day IS NULL OR (billing_day >= 1 AND billing_day <= 28)),
        ADD CONSTRAINT ck_tutor_groups_due_days
            CHECK (due_days >= 0 AND due_days <= 31),
        ADD CONSTRAINT ck_tutor_groups_fee_shape CHECK (
            (fee_mode <> 'monthly' OR billing_day IS NOT NULL)
            AND (fee_mode <> 'package' OR package_lessons IS NOT NULL)
        )
    """,
    """
    ALTER TABLE tutor_group_members
        ADD COLUMN fee_override_uzs INTEGER,
        ADD COLUMN billing_start DATE
    """,
    """
    ALTER TABLE tutor_group_members
        ADD CONSTRAINT ck_tutor_group_members_override CHECK (
            fee_override_uzs IS NULL
            OR (fee_override_uzs >= 0 AND fee_override_uzs <= 1000000000)
        )
    """,
    """
    UPDATE tutor_group_members
    SET billing_start = (created_at AT TIME ZONE 'Asia/Tashkent')::date
    WHERE status = 'active' AND billing_start IS NULL
    """,
    """
    CREATE TABLE tutor_invoices (
        id SERIAL PRIMARY KEY,
        workspace_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        kind VARCHAR(16) NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE,
        lessons_total SMALLINT,
        lessons_used SMALLINT NOT NULL DEFAULT 0,
        amount_uzs INTEGER NOT NULL,
        paid_uzs INTEGER NOT NULL DEFAULT 0,
        due_on DATE NOT NULL,
        status VARCHAR(16) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT fk_tutor_invoices_workspace_id_workspaces
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_tutor_invoices_group_id_tutor_groups
            FOREIGN KEY (group_id) REFERENCES tutor_groups (id) ON DELETE CASCADE,
        CONSTRAINT fk_tutor_invoices_student_id_tutor_students
            FOREIGN KEY (student_id) REFERENCES tutor_students (id) ON DELETE CASCADE,
        CONSTRAINT ck_tutor_invoices_kind CHECK (kind IN ('monthly', 'package')),
        CONSTRAINT ck_tutor_invoices_status
            CHECK (status IN ('due', 'paid', 'overdue', 'waived')),
        CONSTRAINT ck_tutor_invoices_amount
            CHECK (amount_uzs >= 0 AND amount_uzs <= 1000000000),
        CONSTRAINT ck_tutor_invoices_paid
            CHECK (paid_uzs >= 0 AND paid_uzs <= amount_uzs),
        CONSTRAINT ck_tutor_invoices_lessons CHECK (
            lessons_used >= 0
            AND (lessons_total IS NULL OR (
                lessons_total >= 1 AND lessons_total <= 100 AND lessons_used <= lessons_total
            ))
        ),
        CONSTRAINT uq_tutor_invoices_period
            UNIQUE (group_id, student_id, kind, period_start)
    )
    """,
    "CREATE INDEX ix_tutor_invoices_workspace_status ON tutor_invoices (workspace_id, status)",
    "CREATE INDEX ix_tutor_invoices_student_id ON tutor_invoices (student_id)",
    """
    CREATE TABLE tutor_fee_payments (
        id SERIAL PRIMARY KEY,
        invoice_id INTEGER NOT NULL,
        amount_uzs INTEGER NOT NULL,
        paid_on DATE NOT NULL,
        method VARCHAR(16) NOT NULL,
        note VARCHAR(200),
        created_by INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT fk_tutor_fee_payments_invoice_id_tutor_invoices
            FOREIGN KEY (invoice_id) REFERENCES tutor_invoices (id) ON DELETE CASCADE,
        CONSTRAINT fk_tutor_fee_payments_created_by_users
            FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
        CONSTRAINT ck_tutor_fee_payments_amount
            CHECK (amount_uzs > 0 AND amount_uzs <= 1000000000),
        CONSTRAINT ck_tutor_fee_payments_method
            CHECK (method IN ('cash', 'card', 'transfer', 'other'))
    )
    """,
    "CREATE INDEX ix_tutor_fee_payments_invoice_id ON tutor_fee_payments (invoice_id)",
)

_DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE tutor_fee_payments",
    "DROP TABLE tutor_invoices",
    "ALTER TABLE tutor_group_members DROP CONSTRAINT ck_tutor_group_members_override",
    "ALTER TABLE tutor_group_members DROP COLUMN fee_override_uzs, DROP COLUMN billing_start",
    "ALTER TABLE tutor_groups DROP CONSTRAINT ck_tutor_groups_fee_shape",
    "ALTER TABLE tutor_groups DROP CONSTRAINT ck_tutor_groups_due_days",
    "ALTER TABLE tutor_groups DROP CONSTRAINT ck_tutor_groups_billing_day",
    "ALTER TABLE tutor_groups DROP CONSTRAINT ck_tutor_groups_package",
    "ALTER TABLE tutor_groups DROP CONSTRAINT ck_tutor_groups_fee_uzs",
    "ALTER TABLE tutor_groups DROP CONSTRAINT ck_tutor_groups_fee_mode",
    """
    ALTER TABLE tutor_groups
        DROP COLUMN due_days,
        DROP COLUMN billing_day,
        DROP COLUMN package_lessons,
        DROP COLUMN fee_uzs,
        DROP COLUMN fee_mode
    """,
)


def upgrade() -> None:
    """Add course prices, invoices, and the payments recorded against them."""
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Remove course fees. Student status and amount columns stay."""
    for statement in _DOWNGRADE:
        op.execute(statement)
