"""create asset server part view

Revision ID: 0003
Revises: 0002
Create Date: 2025-03-01 10:00:00

"""
from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: None
depends_on: None


def upgrade() -> None:

    # ### 服务器配件行转列 视图 ###
    op.execute("DROP VIEW IF EXISTS ops_assets_parts_info_server_view")
    ops_assets_parts_info_server_view = op.execute("""
        CREATE VIEW ops_assets_parts_info_server_view AS
        select oapi.asset_id, 
        MAX(CASE WHEN oapi.part_type = 'cpu' THEN oapi.part_config else null END) AS 'asset_part_cpu',
        MAX(CASE WHEN oapi.part_type = 'cpu_cores' THEN oapi.part_config else null END) AS 'asset_part_cpu_cores',
        MAX(CASE WHEN oapi.part_type = 'data_disk' THEN oapi.part_config else null END) AS 'asset_part_data_disk',
        MAX(CASE WHEN oapi.part_type = 'disk' THEN oapi.part_config else null END) AS 'asset_part_disk',
        MAX(CASE WHEN oapi.part_type = 'gpu' THEN oapi.part_config else null END) AS 'asset_part_gpu',
        MAX(CASE WHEN oapi.part_type = 'ib_card' THEN oapi.part_config else null END) AS 'asset_part_ib_card',
        MAX(CASE WHEN oapi.part_type = 'memory' THEN oapi.part_config else null END) AS 'asset_part_memory',
        MAX(CASE WHEN oapi.part_type = 'module' THEN oapi.part_config else null END) AS 'asset_part_module',
        MAX(CASE WHEN oapi.part_type = 'nic' THEN oapi.part_config else null END) AS 'asset_part_nic'
        from ops_assets_parts_info oapi where oapi.asset_id is not null group by oapi.asset_id;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS ops_assets_parts_info_server_view")

