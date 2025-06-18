
"""update ops_monitor_url_config_info table

Revision ID: 0015
Revises: 0014
Create Date: 2025-06-18 16:28:45.273721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ops_monitor_url_config_info：修改: url_catalog、url_type、user_id、user_account
    op.alter_column(
        'ops_monitor_url_config_info',
        'url_catalog',
        nullable=True
    )
    op.alter_column(
        'ops_monitor_url_config_info',
        'url_type',
        nullable=True
    )
    op.alter_column(
        'ops_monitor_url_config_info',
        'user_id',
        nullable=True
    )
    op.alter_column(
        'ops_monitor_url_config_info',
        'user_account',
        nullable=True
    )

def downgrade() -> None:
    op.alter_column(
        'ops_monitor_url_config_info',
        'url_catalog',
        nullable=False
    )
    op.alter_column(
        'ops_monitor_url_config_info',
        'url_type',
        nullable=False
    )
    op.alter_column(
        'ops_monitor_url_config_info',
        'user_id',
        nullable=False
    )
    op.alter_column(
        'ops_monitor_url_config_info',
        'user_account',
        nullable=False
    )
