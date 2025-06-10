
"""create ops_resource_metrics_configs table

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-10 16:28:45.273721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('ops_resource_metrics')
    op.drop_table('ops_resource_metrics_configs')

    # ### 资源指标配置信息 ###
    resource_metrics_configs_table = op.create_table(
        "ops_resource_metrics_configs",
        sa.Column("id", sa.String(length=128), nullable=False, comment='资源指标配置信息对象id'),
        sa.Column("name", sa.String(length=128), nullable=False, comment='指标名称'),
        sa.Column("query", sa.String(length=511), nullable=False, comment='指标的promQL语句'),
        sa.Column("description", sa.String(length=255), nullable=True, comment='指标描述信息'),
        sa.Column("sub_class", sa.String(length=128), nullable=True, comment='指标分类'),
        sa.Column("unit", sa.String(length=32), nullable=True, comment='指标单位'),
        sa.Column("extra", sa.Text(), nullable=True, comment='扩展信息'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        comment='资源指标配置信息表'
    )

    # ### 资源指标数据表信息 ###
    resource_metrics_table = op.create_table(
        "ops_resource_metrics",
        sa.Column("id", sa.String(length=128), nullable=False, comment='资源指标对象id'),
        sa.Column("resource_id", sa.String(length=128), nullable=False, comment='资源对象id'),
        sa.Column("name", sa.String(length=128), sa.ForeignKey('ops_resource_metrics_configs.name'), nullable=False, comment='指标名称'),
        sa.Column("data", sa.Text(), nullable=True, comment='指标数据'),
        sa.Column("region", sa.String(length=128), nullable=True, comment='地区（智算中心）'),
        sa.Column("last_modified", sa.DateTime(), nullable=True, comment='最近修改时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='资源指标表'
    )

    # 初始化指标
    op.bulk_insert(resource_metrics_configs_table, [
        {
            "id": "0300dd7d-24c5-11f0-84fe-44a842237864",
            "name": "gpu_count",
            "query": 'count(nvidia_smi_memory_used{host="{host_name}"})',
            "description": 'GPU卡数',
            "sub_class": None,
            "unit": None,
            "extra": None
        },
        {
            "id": "7bebdc86-24c5-11f0-84fe-44a842237864",
            "name": "gpu_power",
            "query": 'avg(nvidia_smi_power_draw{host="{host_name}"})',
            "description": '资源GPU平均功率',
            "sub_class": None,
            "unit": 'watt',
            "extra": None
        },
        {
            "id": "2c3d6b42-24c6-11f0-84fe-44a842237864",
            "name": "cpu_usage",
            "query": '100 - avg(cpu_usage_idle{host="{host_name}"})',
            "description": 'CPU使用率',
            "sub_class": None,
            "unit": 'percent',
            "extra": None
        },
        {
            "id": "3311030e-24c6-11f0-84fe-44a842237864",
            "name": "memory_usage",
            "query": '(mem_used{host="{host_name}"}/mem_total{host="{host_name}"}) *100',
            "description": '内存使用率',
            "sub_class": None,
            "unit": 'percent',
            "extra": None
        },
    ])

def downgrade() -> None:
    op.drop_table('ops_resource_metrics')
    op.drop_table('ops_resource_metrics_configs')

