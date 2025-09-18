"""0026

Revision ID: 0026
Revises: 0025
Create Date: 2025年9月16日20:15:53

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0026'
down_revision: Union[str, None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ops_tenant_harbor_relation_info',
        sa.Column("id", sa.String(length=128), nullable=False, index=True, comment='主键UUID'),
        sa.Column('harbor_name', sa.String(length=128), nullable=True, comment='harbor账号名称'),
        sa.Column('harbor_password', sa.String(length=128), nullable=True, comment='harbor账号密码'),
        sa.Column('tenant_id', sa.String(length=128), nullable=True, comment='租户的id'),
        sa.Column('description', sa.String(length=255), nullable=True, comment='描述'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='租户的Harbor关联关系表'
    )

def downgrade() -> None:
    op.drop_table('ops_tenant_harbor_relation_info')