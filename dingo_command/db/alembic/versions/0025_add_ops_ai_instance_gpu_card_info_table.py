"""0025

Revision ID: 0025
Revises: 0024
Create Date: 2025-08-12 08:25:43.488964

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0025'
down_revision: Union[str, None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ops_ai_instance_gpu_card_info',
        sa.Column("id", sa.String(length=128), nullable=False, index=True, comment='主键UUID'),
        sa.Column('gpu_model_display', sa.String(length=255), nullable=False, comment='页面展示GPU卡型号'),
        sa.Column('gpu_node_label', sa.String(length=255), nullable=False, comment='Node上GPU卡标签'),
        sa.Column('gpu_key', sa.String(length=255), nullable=False, comment='Pod可使用的GPU key值'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        comment='AI GPU卡维护关系表'
    )

def downgrade() -> None:
    op.drop_table('ops_ai_instance_gpu_card_info')