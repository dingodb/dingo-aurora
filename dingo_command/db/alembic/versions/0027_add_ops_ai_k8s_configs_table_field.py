"""0026

Revision ID: 0026
Revises: 0025
Create Date: 2025年9月16日20:15:53

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0027'
down_revision: Union[str, None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ops_ai_k8s_configs', sa.Column('gpu_relation_ib_device', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('ops_ai_k8s_configs', 'gpu_relation_ib_device')