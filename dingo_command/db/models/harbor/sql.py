# 数据表对应的model对象

from __future__ import annotations
from dingo_command.db.engines.mysql import get_session
from dingo_command.db.models.harbor.models import TenantHarborRelation

class HarborRelationSQL:

    @classmethod
    def create_harbor_relation(cls, relation):
        session = get_session()
        with session.begin():
            session.add(relation)
            
    @classmethod
    def update_harbor_relation(cls, relation):
        session = get_session()
        with session.begin():
            session.merge(relation)

    @classmethod
    def delete_harbor_relation_by_id(cls, id):
        session = get_session()
        with session.begin():
            session.query(TenantHarborRelation).filter(TenantHarborRelation.id == id).delete()

    @classmethod
    def get_harbor_relation_by_tenant_id(cls, tenant_id):
        session = get_session()
        with session.begin():
            return session.query(TenantHarborRelation).filter_by(tenant_id=tenant_id).first()