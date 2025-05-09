"""create asset resource relation table

Revision ID: 0005
Revises: 0004
Create Date: 2025-04-21 14:40:00

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: None
depends_on: None


def upgrade() -> None:
    # 增加资产与资源的关联信息表
    op.create_table(
        "ops_assets_resources_relations_info",
        sa.Column("id", sa.String(length=128), nullable=False, comment='关联信息id'),
        sa.Column("asset_id", sa.String(length=128), nullable=True, comment='资产id'),
        sa.Column("resource_id", sa.String(length=128), nullable=True, comment='资源id'),
        sa.Column("resource_type", sa.String(length=128), nullable=True, comment='资源类型'),
        sa.Column("resource_name", sa.String(length=128), nullable=True, comment='资源名称'),
        sa.Column("resource_status", sa.String(length=128), nullable=True, comment='资源状态'),
        sa.Column("resource_project_id", sa.String(length=128), nullable=True, comment='资源所属的project的id'),
        sa.Column("resource_project_name", sa.String(length=128), nullable=True, comment='资源所属的project的名称'),
        sa.Column("resource_user_id", sa.String(length=128), nullable=True, comment='资源所属的用户的id'),
        sa.Column("resource_user_name", sa.String(length=128), nullable=True, comment='资源所属的用户的名称'),
        sa.Column("resource_ip", sa.String(length=256), nullable=True, comment='资源的ip地址'),
        sa.Column("resource_description", sa.String(length=255), nullable=True, comment='资源的描述'),
        sa.Column("resource_extra", sa.Text(), nullable=True, comment='资源的扩展信息'),
        sa.Column("create_date", sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column("update_date", sa.DateTime(), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='资源与资产关联信息表'
    )


def downgrade() -> None:
    # 删除表：ops_assets_resources_relations_info
    op.drop_table('ops_assets_resources_relations_info')

