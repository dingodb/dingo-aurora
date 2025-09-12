"""0024

Revision ID: 0024
Revises: 0023
Create Date: 2025-08-12 08:25:43.488964

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0024'
down_revision: Union[str, None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ops_ai_instance_ports_info',
        sa.Column("id", sa.String(length=128), nullable=False, index=True, comment='主键UUID'),
        sa.Column('instance_id', sa.String(length=128), nullable=False, comment='容器实例的id'),
        sa.Column('instance_svc_port', sa.Integer(), nullable=True, comment='容器实例的服务的port'),
        sa.Column('instance_svc_target_port', sa.Integer(), nullable=True, comment='容器实例的服务的target port'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='AI容器实例端口信息表'
    )
    # 为instance_id字段创建索引
    op.create_index('ix_ops_ai_instance_ports_info_instance_id', 'ops_ai_instance_ports_info', ['instance_id'])


def downgrade() -> None:
    op.drop_index('ix_ops_ai_instance_ports_info_instance_id', table_name='ops_ai_instance_ports_info')
    op.drop_table('ops_ai_instance_ports_info')