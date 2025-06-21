
"""update ops_monitor_url_config_info table

Revision ID: 0016
Revises: 0015
Create Date: 2025-06-21 16:28:45.273721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 为ops_cluster_info表：修改: status_msg字段
    op.alter_column(
        'ops_cluster_info',
        'status_msg',
        type_=mysql.MEDIUMTEXT(),
        existing_type=sa.Text(),
        nullable=True
    )

def downgrade() -> None:
    # 恢复字段类型：Text → String
    op.alter_column(
        'ops_cluster_info',
        'status_msg',
        type_=sa.Text(),
        existing_type=mysql.MEDIUMTEXT(),
        nullable=True
    )

