"""create asset server part view

Revision ID: 0003
Revises: 0002
Create Date: 2025-03-01 10:00:00

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: None
depends_on: None


def upgrade() -> None:
    # 为ops_cluster_info表：修改: status_msg字段
    op.alter_column(
        'ops_cluster_info',
        'status_msg',
        type_=sa.Text(),
        existing_type=sa.String(length=128),
        nullable=True
    )

def downgrade() -> None:
    # 恢复字段类型：Text → String
    op.alter_column(
        'ops_cluster_info',
        'status_msg',
        type_=sa.String(length=128),
        existing_type=sa.Text(),
        nullable=True
    )

