"""add source and source document to portfolios

每筆活動與經歷記錄證明來源（學生填寫、學校獎懲記錄……），以及匯入自哪份上傳的文件。

Revision ID: c4a8f1e2d903
Revises: b7d2e9a41c35
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "c4a8f1e2d903"
down_revision = "b7d2e9a41c35"
branch_labels = None
depends_on = None


def _has_portfolios():
    # 這組 migration 不負責建立基本資料表（正式 MySQL 早已存在）；全新的空資料庫就跳過。
    return sa.inspect(op.get_bind()).has_table("portfolios")


def upgrade():
    if not _has_portfolios():
        return
    with op.batch_alter_table("portfolios") as batch:
        batch.add_column(sa.Column("source", sa.String(length=30), nullable=False, server_default="student"))
        batch.add_column(sa.Column("source_document_id", sa.Integer(), nullable=True))
        batch.create_index("ix_portfolios_source_document_id", ["source_document_id"])
        batch.create_foreign_key("fk_portfolios_source_document_id", "source_documents",
                                 ["source_document_id"], ["id"])


def downgrade():
    if not _has_portfolios():
        return
    with op.batch_alter_table("portfolios") as batch:
        batch.drop_constraint("fk_portfolios_source_document_id", type_="foreignkey")
        batch.drop_index("ix_portfolios_source_document_id")
        batch.drop_column("source_document_id")
        batch.drop_column("source")
