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

    # 插入asset_relation_resource_flag字段
    op.bulk_insert("ops_assets_extends_columns_info",
                   [
                       # 服务器默认配置
                       {'id': '00000000-0a26-11f0-8eb6-b083fee10000', 'asset_type': 'SERVER', 'role_type': None,
                        'column_key': 'asset_relation_resource_flag', 'column_name': '是否关联资源',
                        'column_type': 'str',
                        'required_flag': 0, 'default_flag': 1, 'hidden_flag': 0, 'queue': 30, 'description': None
                        }, ]
                   )

    # 为ops_assets_parts_info表：增加型号：part_model字段
    op.add_column('ops_assets_basic_info',
                  sa.Column('asset_relation_resource_flag', sa.Boolean, nullable=True, default=0))


def downgrade() -> None:
    # 删除表：ops_assets_resources_relations_info
    op.drop_table('ops_assets_resources_relations_info')

    # 移除asset_relation_resource_flag数据
    op.execute("DELETE FROM ops_assets_extends_columns_info WHERE column_key='asset_relation_resource_flag';")

    # 移除字段：asset_relation_resource_flag
    op.drop_column('ops_assets_basic_info', 'asset_relation_resource_flag')

