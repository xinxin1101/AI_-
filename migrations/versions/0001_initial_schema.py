"""initial production backend schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("session_id", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("session_id", sa.Text(), sa.ForeignKey("conversations.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_messages_session_created", "messages", ["session_id", "created_at"])
    op.create_table(
        "traces",
        sa.Column("trace_id", sa.Text(), primary_key=True),
        sa.Column("session_id", sa.Text(), sa.ForeignKey("conversations.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_message", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("gate_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("fallback", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("idx_traces_session_started", "traces", ["session_id", "started_at"])
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("trace_id", sa.Text(), sa.ForeignKey("traces.trace_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("circuit_state", sa.Text(), nullable=True),
    )
    op.create_index("idx_tool_calls_trace", "tool_calls", ["trace_id"])
    op.create_table(
        "citations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("trace_id", sa.Text(), sa.ForeignKey("traces.trace_id", ondelete="CASCADE"), nullable=False),
        sa.Column("citation_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
    )
    op.create_index("idx_citations_trace", "citations", ["trace_id"])
    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("session_id", sa.Text(), sa.ForeignKey("conversations.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_feedback_session_created", "feedback", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_feedback_session_created", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("idx_citations_trace", table_name="citations")
    op.drop_table("citations")
    op.drop_index("idx_tool_calls_trace", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_index("idx_traces_session_started", table_name="traces")
    op.drop_table("traces")
    op.drop_index("idx_messages_session_created", table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversations")
