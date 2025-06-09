"""create asset server part view

Revision ID: 0003
Revises: 0002
Create Date: 2025-03-01 10:00:00

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: None
depends_on: None


def upgrade() -> None:
    op.add_column('ops_cluster_info', sa.Column('admin_network_name',
                                             sa.String(length=128), nullable=True))
    op.add_column('ops_cluster_info', sa.Column('admin_network_cidr',
                                                sa.String(length=128), nullable=True))
    op.add_column('ops_cluster_info', sa.Column('bus_network_name',
                                                 sa.String(length=128), nullable=True))
    op.add_column('ops_cluster_info', sa.Column('bus_network_cidr',
                                                sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('ops_cluster_info', 'admin_network_name')
    op.drop_column('ops_cluster_info', 'admin_network_cidr')
    op.drop_column('ops_cluster_info', 'bus_network_name')
    op.drop_column('ops_cluster_info', 'bus_network_cidr')

