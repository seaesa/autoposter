"""rename access_token_encrypted to access_token

Revision ID: ef01fc8e8417
Revises: f2fdfee2dc29
Create Date: 2026-08-07 13:31:36.171310

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'ef01fc8e8417'
down_revision = 'f2fdfee2dc29'
branch_labels = None
depends_on = None


def upgrade():
    # dữ liệu cũ là Fernet-encrypted; bỏ mã hóa → xóa cột, thêm mới plain (user nhập lại token)
    op.drop_column("facebookpage", "access_token_encrypted")
    op.add_column(
        "facebookpage", sa.Column("access_token", sa.String(), nullable=True)
    )


def downgrade():
    op.drop_column("facebookpage", "access_token")
    op.add_column(
        "facebookpage",
        sa.Column("access_token_encrypted", sa.String(), nullable=True),
    )
