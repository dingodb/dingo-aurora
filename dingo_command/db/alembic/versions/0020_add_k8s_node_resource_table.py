
"""add ops_ai_instance_info table

Revision ID: 0020
Revises: 0019

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0020'
down_revision: Union[str, None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "ops_ai_k8s_node_resource",
        sa.Column("id", sa.String(length=128), nullable=False, server_default=sa.text("UUID()"), comment='主键UUID'),
        sa.Column("k8s_id", sa.String(length=128), nullable=True, comment='k8s_id'),
        sa.Column("node_name", sa.String(length=128), nullable=True, comment='节点名称'),
        sa.Column("less_gpu_pod_count", sa.Integer(), nullable=True, default=0 , comment='无GPU卡pod数目'),
        sa.Column("gpu_model", sa.String(length=128), nullable=True, comment='gpu型号'),
        sa.Column("gpu_total", sa.String(length=128), nullable=True, comment='gpu总量'),
        sa.Column("gpu_used", sa.String(length=128), nullable=True, comment='gpu已用量'),
        sa.Column("cpu_total", sa.String(length=128), nullable=True, comment='cpu总量'),
        sa.Column("cpu_used", sa.String(length=128), nullable=True, comment='cpu已用量'),
        sa.Column("memory_total", sa.String(length=128), nullable=True, comment='内存总量'),
        sa.Column("memory_used", sa.String(length=128), nullable=True, comment='内存已用量'),
        sa.Column("storage_total", sa.String(length=128), nullable=True, comment='存储总量'),
        sa.Column("storage_used", sa.String(length=128), nullable=True, comment='存储已用量'),
        sa.Column("update_time", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='AI K8s node resource信息表'
    )
    op.create_index(op.f('ix_ops_ai_k8s_node_resource_id'), 'ops_ai_k8s_node_resource', ['id'], unique=False)
    op.create_index(op.f('ix_ops_ai_k8s_node_resource_k8s_id'), 'ops_ai_k8s_node_resource', ['k8s_id'], unique=False)
    op.create_index(op.f('ix_ops_ai_k8s_node_resource_node_name'), 'ops_ai_k8s_node_resource', ['node_name'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_ops_ai_k8s_node_resource_id'), table_name='ops_ai_k8s_node_resource')
    op.drop_index(op.f('ix_ops_ai_k8s_node_resource_k8s_id'), table_name='ops_ai_k8s_node_resource')
    op.drop_index(op.f('ix_ops_ai_k8s_node_resource_node_name'), table_name='ops_ai_k8s_node_resource')
    op.drop_table('ops_ai_k8s_node_resource')
