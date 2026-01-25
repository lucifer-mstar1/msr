"""Expand test_questions.correct_answer to Text for multi answers.

Revision ID: 0002_expand_correct_answer_text
Revises: 0001_init
Create Date: 2026-01-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_expand_correct_answer_text"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite needs batch operations for type change
    with op.batch_alter_table("test_questions") as batch:
        batch.alter_column(
            "correct_answer",
            existing_type=sa.String(length=32),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("test_questions") as batch:
        batch.alter_column(
            "correct_answer",
            existing_type=sa.Text(),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
