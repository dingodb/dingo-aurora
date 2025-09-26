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
    def update_harbor_relation(cls, relation=None, id=None, harbor_password=None):
        session = get_session()
        with session.begin():
            if relation:
                # 如果传入了完整的relation对象，直接merge
                session.merge(relation)
            elif id and harbor_password:
                # 如果传入了id和harbor_password，根据id更新密码
                session.query(TenantHarborRelation).filter(TenantHarborRelation.id == id).update({
                    TenantHarborRelation.harbor_password: harbor_password
                })
            else:
                raise ValueError("必须提供relation对象或者id和harbor_password参数")

    @classmethod
    def delete_harbor_relation_by_id(cls, id):
        session = get_session()
        with session.begin():
            session.query(TenantHarborRelation).filter(TenantHarborRelation.id == id).delete()

    @classmethod
    def get_harbor_relation_by_tenant_id(cls, tenant_id=None, username=None):
        session = get_session()
        with session.begin():
            if tenant_id:
                return session.query(TenantHarborRelation).filter_by(tenant_id=tenant_id).first()
            elif username:
                return session.query(TenantHarborRelation).filter_by(harbor_name=username).first()