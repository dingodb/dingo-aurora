"""create asset server part view

Revision ID: 0003
Revises: 0002
Create Date: 2025-03-01 10:00:00

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: None
depends_on: None


def upgrade() -> None:
    # 为ops_assets_parts_info表：增加型号：part_model字段
    op.add_column('ops_assets_parts_info', sa.Column('part_model', sa.String(length=128), nullable=True))
    # 为ops_assets_parts_info表：增加采购合同编号：purchase_contract_number字段
    op.add_column('ops_assets_parts_info', sa.Column('purchase_contract_number', sa.String(length=128), nullable=True))
    # 为ops_assets_parts_info表：增加位置：position字段
    op.add_column('ops_assets_parts_info', sa.Column('position', sa.String(length=65535), nullable=True))
    # 为ops_assets_parts_info表：增加是否固定资产：fixed_flag字段
    op.add_column('ops_assets_parts_info', sa.Column('fixed_flag', sa.Boolean(), nullable=True, default=0))

    # 增加资产配件关联信息表
    op.create_table(
        "ops_assets_parts_relations_info",
        sa.Column("id", sa.String(length=128), nullable=False, comment='资产配件关联信息id'),
        sa.Column("asset_part_id", sa.String(length=128), nullable=False, comment='资产配件id'),
        sa.Column("part_sn", sa.String(length=128), nullable=False, comment='资产配件序列号SN'),
        sa.PrimaryKeyConstraint('id'),
        comment='资产配件关联信息表'
    )


def downgrade() -> None:
    # 移除型号：part_model字段
    op.drop_column('ops_assets_parts_info', 'part_model')
    # 移除采购合同编号：purchase_contract_number字段
    op.drop_column('ops_assets_parts_info', 'purchase_contract_number')
    # 移除位置：position字段
    op.drop_column('ops_assets_parts_info', 'position')
    # 移除是否固定资产：fixed_flag字段
    op.drop_column('ops_assets_parts_info', 'fixed_flag')

    # 移除表：ops_assets_parts_relations_info
    op.drop_table('ops_assets_parts_relations_info')

