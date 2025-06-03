"""create asset server part view

Revision ID: 0003
Revises: 0002
Create Date: 2025-03-01 10:00:00

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: None
depends_on: None


def upgrade() -> None:
    # 为ops_assets_resources_relations_info表：增加: node_name字段
    op.add_column('ops_assets_resources_relations_info', sa.Column('node_name', sa.String(length=128), nullable=True, comment='节点名称'))


def downgrade() -> None:
    # 移除：node_name字段
    op.drop_column('ops_assets_resources_relations_info', 'node_name')

