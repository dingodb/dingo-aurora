
"""add ops_ai_instance_info table

Revision ID: 0019
Revises: 0018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "ops_ai_instance_info",
        sa.Column("id", sa.String(length=128), nullable=False, server_default=sa.text("UUID()"), comment='主键UUID'),
        sa.Column("instance_name", sa.String(length=128), nullable=True, comment='容器实例名称(页面输入名称)'),
        sa.Column("instance_real_name", sa.String(length=128), nullable=True, comment='容器实例名称(底层sts名称)'),
        sa.Column("instance_node_name", sa.String(length=128), nullable=True, comment='POD所在node名称'),
        sa.Column("instance_status", sa.String(length=128), nullable=True, comment='上层容器实例状态'),
        sa.Column("instance_real_status", sa.String(length=128), nullable=True, comment='底层容器实例真实状态'),
        sa.Column("instance_k8s_type", sa.String(length=128), nullable=True, comment='k8s类型'),
        sa.Column("instance_k8s_id", sa.String(length=128), nullable=True, comment='k8s ID'),
        sa.Column("instance_k8s_name", sa.String(length=128), nullable=True, comment='k8s名称'),
        sa.Column("instance_project_id", sa.String(length=128), nullable=True, comment='项目ID'),
        sa.Column("instance_project_name", sa.String(length=128), nullable=True, comment='项目名称'),
        sa.Column("instance_user_id", sa.String(length=128), nullable=True, comment='用户ID'),
        sa.Column("instance_user_name", sa.String(length=128), nullable=True, comment='用户名称'),
        sa.Column("instance_root_account_id", sa.String(length=128), nullable=True, comment='用户所属主账号ID'),
        sa.Column("instance_root_account_name", sa.String(length=128), nullable=True, comment='用户所属主账号名称'),
        sa.Column("instance_image", sa.String(length=255), nullable=True, comment='镜像信息'),
        sa.Column("image_type", sa.String(length=255), nullable=True, comment='实例的镜像库'),
        sa.Column("stop_time", sa.DateTime(), nullable=True, comment='自动关机时间'),
        sa.Column("auto_delete_time", sa.DateTime(), nullable=True, comment='自动释放时间'),
        sa.Column("instance_config", sa.Text(), nullable=True, comment='实例的计算资源配置(JSON格式)'),
        sa.Column("instance_volumes", sa.Text(), nullable=True, comment='实例的卷配置(JSON格式)'),
        sa.Column("instance_envs", sa.Text(), nullable=True, comment='环境变量信息(JSON格式)'),
        sa.Column("error_msg", sa.Text(), nullable=True, comment='错误信息'),
        sa.Column("instance_description", sa.Text(), nullable=True, comment='描述信息'),
        sa.Column("instance_create_time", sa.DateTime(), nullable=True, comment='实例创建时间'),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment='创建时间'),
        sa.Column("update_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='AI容器实例信息表'
    )
    op.create_index(op.f('ix_ops_ai_instance_info_id'), 'ops_ai_instance_info', ['id'], unique=False)
    op.create_index(op.f('ix_ops_ai_instance_info_instance_k8s_id'), 'ops_ai_instance_info', ['instance_k8s_id'], unique=False)

def downgrade() -> None:
    op.create_index(op.f('ix_ops_ai_instance_info_id'), 'ops_ai_instance_info', ['id'], unique=False)
    op.create_index(op.f('ix_ops_ai_instance_info_instance_k8s_id'), 'ops_ai_instance_info', ['instance_k8s_id'], unique=False)
    op.drop_table('ops_ai_instance_info')
