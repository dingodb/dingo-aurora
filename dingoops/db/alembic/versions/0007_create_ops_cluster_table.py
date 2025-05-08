
"""create ops_resource_metrics_configs table

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-10 16:28:45.273721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 资源指标配置信息 ###
    cluster_info_table = op.create_table(
        "ops_cluster_info",
        sa.Column("id", sa.String(length=128), primary_key=True, nullable=False, index=True, comment='集群ID'),
        sa.Column("name", sa.String(length=128), primary_key=True, nullable=False, index=True, comment='集群名称'),
        sa.Column("project_id", sa.String(length=128), nullable=True, comment='项目ID'),
        sa.Column("user_id", sa.String(length=128), nullable=True, comment='用户ID'),
        sa.Column("labels", sa.String(length=128), nullable=True, comment='标签'),
        sa.Column("status", sa.String(length=128), nullable=True, comment='集群状态'),
        sa.Column("status_msg", sa.String(length=128), nullable=True, comment='状态信息'),
        sa.Column("region_name", sa.String(length=128), nullable=True, comment='区域名称'),
        sa.Column("admin_network_id", sa.String(length=128), nullable=True, comment='管理网络ID'),
        sa.Column("admin_subnet_id", sa.String(length=128), nullable=True, comment='管理子网ID'),
        sa.Column("bus_network_id", sa.String(length=128), nullable=True, comment='业务网络ID'),
        sa.Column("bus_subnet_id", sa.String(length=128), nullable=True, comment='业务子网ID'),
        sa.Column("type", sa.String(length=128), nullable=True, comment='集群类型'),
        sa.Column("kube_info", sa.Text(), nullable=True, comment='kubernetes信息'),
        sa.Column("create_time", sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column("update_time", sa.DateTime(), nullable=True, comment='更新时间'),
        sa.Column("description", sa.String(length=255), nullable=True, comment='描述信息'),
        sa.Column("cpu", sa.Integer(), nullable=True, comment='CPU资源'),
        sa.Column("mem", sa.Integer(), nullable=True, comment='内存资源'),
        sa.Column("gpu", sa.Integer(), nullable=True, comment='GPU资源'),
        sa.Column("gpu_mem", sa.Integer(), nullable=True, comment='GPU内存'),
        sa.Column("extra", sa.Text(), nullable=True, comment='扩展信息'),
        sa.Column("private_key", sa.Text(), nullable=True, comment='私钥信息'),
        sa.PrimaryKeyConstraint('id', 'name'),
        comment='集群信息表'
    )
    # ### 资源指标数据表信息 ###
    cluster_params_table = op.create_table(
        "ops_cluster_params",
        sa.Column("key", sa.String(length=128), primary_key=True, nullable=False, index=True, comment='参数键'),
        sa.Column("value", sa.String(length=255), nullable=True, comment='参数值'),
        sa.PrimaryKeyConstraint('key'),
        comment='集群参数表'
    )
        # ### 任务信息表 ###
    task_info_table = op.create_table(
        "ops_task_info",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, index=True, comment='任务ID'),
        sa.Column("cluster_id", sa.String(length=128), nullable=True, comment='关联集群ID'),
        sa.Column("task_id", sa.String(length=128), nullable=True, comment='任务标识'),
        sa.Column("state", sa.String(length=128), nullable=True, comment='任务状态'),
        sa.Column("msg", sa.String(length=128), nullable=True, comment='任务消息'),
        sa.Column("detail", sa.String(length=128), nullable=False, default="0", comment='任务详情'),
        sa.Column("start_time", sa.DateTime(), nullable=True, comment='开始时间'),
        sa.Column("end_time", sa.DateTime(), nullable=True, comment='结束时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='任务信息表'
    )

    # 初始化指标
    op.bulk_insert(cluster_params_table, [
        {
            "key": "apiserver_pulic_ip_access",
            "value": "true"
        },
        {
            "key": "kube-proxy",
            "value": "iptables,ipvs"
        },
        {
            "key": "kubernetes_version",
            "value": "v1.32.0,v1.31.5"
        },
        {
            "key": "network_plugin",
            "value": "calico"
        },
        {
            "key": "runtime",
            "value": "containerd,docker"
        },
                {
            "key": "service_cidr",
            "value": "10.10.0.0/32,192.168.0.0/24"
        }
    ])

def downgrade() -> None:
    op.drop_table('ops_task_info')
    op.drop_table('ops_cluster_params')
    op.drop_table('ops_cluster_info')

