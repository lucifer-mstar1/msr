"""init

Revision ID: 0001_init
Revises:
Create Date: 2025-12-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tg_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("is_registered", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_baseline", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tg_id", name="uq_users_tg_id"),
    )
    op.create_index("ix_users_tg_id", "users", ["tg_id"])

    op.create_table(
        "tests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("num_questions", sa.Integer(), nullable=False),
        sa.Column("pdf_path", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("is_rasch", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("category", "name", name="uq_tests_category_name"),
    )
    op.create_index("ix_tests_category", "tests", ["category"])

    op.create_table(
        "test_questions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("test_id", sa.Integer(), sa.ForeignKey("tests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("q_num", sa.Integer(), nullable=False),
        sa.Column("correct_answer", sa.String(length=32), nullable=False, server_default=""),
        sa.UniqueConstraint("test_id", "q_num", name="uq_test_questions_test_qnum"),
    )
    op.create_index("ix_test_questions_test_id", "test_questions", ["test_id"])

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_id", sa.Integer(), sa.ForeignKey("tests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answers_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("raw_correct", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_rasch", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"])
    op.create_index("ix_submissions_test_id", "submissions", ["test_id"])


def downgrade() -> None:
    op.drop_index("ix_submissions_test_id", table_name="submissions")
    op.drop_index("ix_submissions_user_id", table_name="submissions")
    op.drop_table("submissions")

    op.drop_index("ix_test_questions_test_id", table_name="test_questions")
    op.drop_table("test_questions")

    op.drop_index("ix_tests_category", table_name="tests")
    op.drop_table("tests")

    op.drop_index("ix_users_tg_id", table_name="users")
    op.drop_table("users")

    op.drop_table("settings")
