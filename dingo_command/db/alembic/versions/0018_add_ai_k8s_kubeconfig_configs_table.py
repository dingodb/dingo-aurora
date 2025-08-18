
"""add ops_ai_k8s_kubeconfig_configs table

Revision ID: 0018
Revises: 0017
Create Date: 2025-06-21 16:28:45.273721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ops_ai_k8s_kubeconfig_configs",
        sa.Column("id", sa.String(length=128), nullable=False, comment='主键id'),
        sa.Column("k8s_id", sa.String(length=128), nullable=False, unique=True, comment='k8s集群ID（唯一）'),
        sa.Column("k8s_name", sa.String(length=128), nullable=False, unique=True, comment='k8s集群名称'),
        sa.Column("k8s_type", sa.String(length=128), nullable=False, comment='k8s集群类型'),
        sa.Column("kubeconfig_path", sa.String(length=255), nullable=True, comment='k8s集群kube-config文件路径'),
        sa.Column("kubeconfig_context_name", sa.String(length=128), nullable=True, comment='k8s集群kube-config context admin name'),
        sa.Column("kubeconfig", sa.Text(), nullable=True, comment='k8s集群kube-config内容'),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"),comment='创建时间'),
        sa.Column("update_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment='更新时间'),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('k8s__id', name='uq_k8s__id'),  # 显式定义唯一约束
        comment='AI k8s集群kube-config配置表'
    )

def downgrade() -> None:
    op.drop_table('ops_ai_k8s_kubeconfig_configs')