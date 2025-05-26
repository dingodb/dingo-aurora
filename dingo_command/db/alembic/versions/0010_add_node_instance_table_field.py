"""create asset server part view

Revision ID: 0003
Revises: 0002
Create Date: 2025-03-01 10:00:00

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: None
depends_on: None


def upgrade() -> None:
    # 为ops_instance_info表：增加: status_msg字段
    # 为ops_node_info表：增加: status_msg字段
    op.add_column('ops_instance_info', sa.Column('status_msg', sa.Text(), nullable=True))
    op.add_column('ops_node_info', sa.Column('status_msg', sa.Text(), nullable=True))
    op.add_column('ops_node_info', sa.Column('floating_forward_ip',
                                             sa.String(length=128), nullable=True))
    op.add_column('ops_node_info', sa.Column('ip_forward_rule', sa.JSON(), nullable=True))
    op.add_column('ops_instance_info', sa.Column('floating_forward_ip',
                                                 sa.String(length=128), nullable=True))
    op.add_column('ops_instance_info', sa.Column('ip_forward_rule', sa.JSON(), nullable=True))


def downgrade() -> None:
    # 移除：status_msg字段
    op.drop_column('ops_instance_info', 'status_msg')
    op.drop_column('ops_instance_info', 'floating_forward_ip')
    op.drop_column('ops_instance_info', 'ip_forward_rule')
    # 移除：status_msg字段
    op.drop_column('ops_node_info', 'status_msg')
    op.drop_column('ops_node_info', 'floating_forward_ip')
    op.drop_column('ops_node_info', 'ip_forward_rule')

