
"""create ops_resource_metrics_configs table

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-10 16:28:45.273721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 外部报送json消息信息表 ###
    op.create_table(
        "ops_external_message",
        sa.Column("id", sa.String(length=128), nullable=False, comment='消息id'),
        sa.Column("message_type", sa.String(length=128), nullable=True, comment='消息类型'),
        sa.Column("region_name", sa.String(length=128), nullable=True, comment='地区名称'),
        sa.Column("az_name", sa.String(length=128), nullable=True, comment='AZ名称'),
        sa.Column("message_status", sa.String(length=40), nullable=True, comment='地区名称'),
        sa.Column("message_data", sa.Text(), nullable=True, comment='外部信息内容'),
        sa.Column("message_description", sa.Text, nullable=True, comment='描述信息'),
        sa.Column("create_date", sa.DateTime(), nullable=True),
        sa.Column("update_date", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        comment='外部报送消息信息表'
    )


def downgrade() -> None:
    op.drop_table('ops_external_message')

