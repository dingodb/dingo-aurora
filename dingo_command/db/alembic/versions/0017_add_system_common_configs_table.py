
"""update ops_monitor_url_config_info table

Revision ID: 0017
Revises: 0016
Create Date: 2025-06-21 16:28:45.273721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0017'
down_revision: Union[str, None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    system_common_configs_table = op.create_table(
        "system_common_configs",
        sa.Column("config_key", sa.Text(), nullable=True, comment='配置key值'),
        sa.Column("config_value", sa.Text(), nullable=True, comment='配置value值'),
        sa.UniqueConstraint('config_key'),
        comment='系统通用配置'
    )

    # 初始化指标
    op.bulk_insert(system_common_configs_table, [
        {
            "config_key": "enable_k8s",
            "config_value": "false",
        }
    ])

def downgrade() -> None:
    op.drop_table('system_common_configs')