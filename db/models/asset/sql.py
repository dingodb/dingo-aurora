# 数据表对应的model对象

from __future__ import annotations

from sqlalchemy.orm import sessionmaker, aliased
from sqlalchemy import create_engine, func
from typing_extensions import assert_type

from db.engines.mysql import get_session
from db.models.asset.models import Asset, AssetBasicInfo, AssetPartsInfo, AssetManufacturesInfo, AssetPositionsInfo, \
    AssetContractsInfo, AssetBelongsInfo, AssetCustomersInfo, AssetType, AssetFlowsInfo, AssetManufactureRelationInfo, \
    AssetExtendsColumnsInfo

from enum import Enum

#链接数据库，可以使用配置文件进行定义
# engine = create_engine("mysql+pymysql://root:HworLIIDvmTRsPfQauNskuJF8PcoTuULfu3dEHFg@10.220.56.254:3306/dingoops?charset=utf8mb3", echo=True)
# 资产排序字段字典
asset_dir_dic= {"frame_position":AssetPositionsInfo.frame_position, "asset_status":AssetBasicInfo.asset_status, "asset_name":AssetBasicInfo.name, "id": AssetBasicInfo.id}
# 配件的所有列
part_columns = [getattr(AssetPartsInfo, column.name).label(column.name) for column in AssetPartsInfo.__table__.columns]
# 流的所有列
flow_columns = [getattr(AssetFlowsInfo, column.name).label(column.name) for column in AssetFlowsInfo.__table__.columns]

class AssetSQL:

    @classmethod
    def list_asset(cls, query_params, page=1, page_size=10, sort_keys=None, sort_dirs="ascend"):
        # 获取session
        session = get_session()
        with session.begin():
            # 查询语句
            query = session.query(AssetBasicInfo.id.label("id"),
                                  AssetBasicInfo.name.label("name"),
                                  AssetBasicInfo.asset_type_id.label("asset_type_id"),
                                  AssetBasicInfo.asset_category.label("asset_category"),
                                  AssetBasicInfo.asset_type.label("asset_type"),
                                  AssetBasicInfo.equipment_number.label("equipment_number"),
                                  AssetBasicInfo.sn_number.label("sn_number"),
                                  AssetBasicInfo.asset_number.label("asset_number"),
                                  AssetBasicInfo.asset_status.label("asset_status"),
                                  AssetBasicInfo.asset_status_description.label("asset_status_description"),
                                  AssetBasicInfo.description.label("description"),
                                  AssetBasicInfo.extra.label("extra"),
                                  AssetBasicInfo.extend_column_extra.label("extend_column_extra"),
                                  AssetType.asset_type_name_zh.label("asset_type_name_zh"),
                                  AssetManufacturesInfo.id.label("manufacture_id"),
                                  AssetManufacturesInfo.name.label("manufacture_name"),
                                  AssetManufacturesInfo.description.label("manufacture_description"),
                                  AssetManufacturesInfo.extra.label("manufacture_extra"),
                                  AssetPositionsInfo.id.label("position_id"),
                                  AssetPositionsInfo.frame_position.label("position_frame_position"),
                                  AssetPositionsInfo.cabinet_position.label("position_cabinet_position"),
                                  AssetPositionsInfo.u_position.label("position_u_position"),
                                  AssetPositionsInfo.description.label("position_description"),
                                  AssetContractsInfo.id.label("contract_id"),
                                  AssetContractsInfo.contract_number.label("contract_number"),
                                  AssetContractsInfo.purchase_date.label("contract_purchase_date"),
                                  AssetContractsInfo.batch_number.label("contract_batch_number"),
                                  AssetContractsInfo.description.label("contract_description"),
                                  AssetBelongsInfo.id.label("belong_id"),
                                  AssetBelongsInfo.department_id.label("belong_department_id"),
                                  AssetBelongsInfo.department_name.label("belong_department_name"),
                                  AssetBelongsInfo.user_id.label("belong_user_id"),
                                  AssetBelongsInfo.user_name.label("belong_user_name"),
                                  AssetBelongsInfo.tel_number.label("belong_tel_number"),
                                  AssetBelongsInfo.description.label("belong_contract_description"),
                                  AssetCustomersInfo.id.label("customer_id"),
                                  AssetCustomersInfo.customer_id.label("customer_customer_id"),
                                  AssetCustomersInfo.customer_name.label("customer_customer_name"),
                                  AssetCustomersInfo.rental_duration.label("customer_rental_duration"),
                                  AssetCustomersInfo.start_date.label("customer_start_date"),
                                  AssetCustomersInfo.end_date.label("customer_end_date"),
                                  AssetCustomersInfo.vlan_id.label("customer_vlan_id"),
                                  AssetCustomersInfo.float_ip.label("customer_float_ip"),
                                  AssetCustomersInfo.band_width.label("customer_band_width"),
                                  AssetCustomersInfo.description.label("customer_description"),
                                  )
            # 外连接
            query = query.outerjoin(AssetManufactureRelationInfo, AssetManufactureRelationInfo.asset_id == AssetBasicInfo.id). \
                outerjoin(AssetManufacturesInfo, AssetManufacturesInfo.id == AssetManufactureRelationInfo.manufacture_id). \
                outerjoin(AssetType, AssetType.id == AssetBasicInfo.asset_type_id). \
                outerjoin(AssetPositionsInfo, AssetPositionsInfo.asset_id == AssetBasicInfo.id). \
                outerjoin(AssetContractsInfo, AssetContractsInfo.asset_id == AssetBasicInfo.id). \
                outerjoin(AssetBelongsInfo, AssetBelongsInfo.asset_id == AssetBasicInfo.id). \
                outerjoin(AssetCustomersInfo, AssetCustomersInfo.asset_id == AssetBasicInfo.id)
            # 数据库查询参数
            if "asset_name" in query_params and query_params["asset_name"]:
                query = query.filter(AssetBasicInfo.name.like('%' + query_params["asset_name"] + '%'))
            if "asset_id" in query_params and query_params["asset_id"]:
                query = query.filter(AssetBasicInfo.id == query_params["asset_id"])
            if "asset_ids" in query_params and query_params["asset_ids"]:
                query = query.filter(AssetBasicInfo.id.in_(query_params["asset_ids"].split(',')))
            if "asset_category" in query_params and query_params["asset_category"]:
                query = query.filter(AssetBasicInfo.asset_category == query_params["asset_category"])
            if "asset_type" in query_params and query_params["asset_type"]:
                query = query.filter(AssetBasicInfo.asset_type.like('%' + query_params["asset_type"] + '%'))
            if "asset_status" in query_params and query_params["asset_status"]:
                query = query.filter(AssetBasicInfo.asset_status == query_params["asset_status"])
            if "frame_position" in query_params and query_params["frame_position"]:
                query = query.filter(AssetPositionsInfo.frame_position.like('%' + query_params["frame_position"] + '%'))
            if "cabinet_position" in query_params and query_params["cabinet_position"]:
                query = query.filter(AssetPositionsInfo.cabinet_position.like('%' + query_params["cabinet_position"] + '%'))
            if "u_position" in query_params and query_params["u_position"]:
                query = query.filter(AssetPositionsInfo.u_position.like('%' + query_params["u_position"] + '%'))
            if "equipment_number" in query_params and query_params["equipment_number"]:
                query = query.filter(AssetBasicInfo.equipment_number.like('%' + query_params["equipment_number"] + '%'))
            if "asset_number" in query_params and query_params["asset_number"]:
                query = query.filter(AssetBasicInfo.asset_number.like('%' + query_params["asset_number"] + '%'))
            if "sn_number" in query_params and query_params["sn_number"]:
                query = query.filter(AssetBasicInfo.sn_number.like('%' + query_params["sn_number"] + '%'))
            if "department_name" in query_params and query_params["department_name"]:
                query = query.filter(AssetBelongsInfo.department_name.like('%' + query_params["department_name"] + '%'))
            if "user_name" in query_params and query_params["user_name"]:
                query = query.filter(AssetBelongsInfo.user_name.like('%' + query_params["user_name"] + '%'))
            if "manufacture_name" in query_params and query_params["manufacture_name"]:
                query = query.filter(AssetManufacturesInfo.name.like('%' + query_params["manufacture_name"] + '%'))
            # 总数
            count = query.count()
            # 排序
            if sort_keys is not None and sort_keys in asset_dir_dic:
                if sort_dirs == "ascend" or sort_dirs is None :
                    query = query.order_by(asset_dir_dic[sort_keys].asc())
                elif sort_dirs == "descend":
                    query = query.order_by(asset_dir_dic[sort_keys].desc())
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            assert_list = query.all()
            # 返回
            return count, assert_list


    @classmethod
    def list_asset_basic_info(cls, asset_name=None, page=1, page_size=10, field=None, dir="ascend"):
        # Session = sessionmaker(bind=engine,expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            query = session.query(AssetBasicInfo)
            # 数据库查询参数
            if asset_name is not None:
                query = query.filter(AssetBasicInfo.name.like('%' + asset_name + '%'))

            # 总数
            count = query.count()
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            assert_list = query.all()
            # 返回
            return count, assert_list


    @classmethod
    def get_asset_basic_info_by_id(cls, id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.query(AssetBasicInfo).filter(AssetBasicInfo.id == id).first()

    @classmethod
    def get_asset_basic_info_by_catalog_name(cls, catalog, name):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.query(AssetBasicInfo).filter(AssetBasicInfo.asset_category == catalog).filter(AssetBasicInfo.name == name).first()

    @classmethod
    def get_asset_basic_info_by_asset_number(cls, asset_number):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.query(AssetBasicInfo).filter(AssetBasicInfo.asset_number == asset_number).first()


    @classmethod
    def update_asset_basic_info(cls, asset_basic_info_db):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.merge(asset_basic_info_db)


    @classmethod
    def create_asset_basic_info(cls, data):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(data)


    @classmethod
    def create_asset(cls, basic_info, manufacture_info, manufacture_relation_info, position_info, contract_info, belong_info, customer_info, part_info, flow_info):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(basic_info)
            if manufacture_info is not None:
                session.add(manufacture_info)
            if manufacture_relation_info is not None:
                session.add(manufacture_relation_info)
            if position_info is not None:
                session.add(position_info)
            if contract_info is not None:
                session.add(contract_info)
            if belong_info is not None:
                session.add(belong_info)
            if customer_info is not None:
                session.add(customer_info)
            if part_info:
                session.add_all(part_info)
            if flow_info:
                session.add_all(flow_info)


    @classmethod
    def update_asset(cls, basic_info, manufacture_info, manufacture_relation_info, position_info, contract_info, belong_info, customer_info, part_info, flow_info):
        session = get_session()
        with session.begin():
            if basic_info:
                session.merge(basic_info)
            if manufacture_info and manufacture_info.name:
                session.add(manufacture_info)
            if manufacture_relation_info:
                session.query(AssetManufactureRelationInfo).filter(AssetManufactureRelationInfo.asset_id == basic_info.id).delete()
                session.add(manufacture_relation_info)
            if position_info:
                session.merge(position_info)
            if contract_info:
                session.merge(contract_info)
            if belong_info:
                session.merge(belong_info)
            if customer_info:
                session.merge(customer_info)
            if part_info:
                session.query(AssetPartsInfo).filter(AssetPartsInfo.id == basic_info.id).delete()
                session.add_all(part_info)
            if flow_info:
                session.add_all(flow_info)


    @classmethod
    def delete_asset(cls, asset_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            # 删除资产基础信息
            session.query(AssetBasicInfo).filter(AssetBasicInfo.id == asset_id).delete()
            # 删除资产的配件信息
            session.query(AssetPartsInfo).filter(AssetPartsInfo.asset_id == asset_id).delete()
            # 删除资产的关联厂商信息
            session.query(AssetManufactureRelationInfo).filter(AssetManufactureRelationInfo.asset_id == asset_id).delete()
            # 删除资产的位置信息
            session.query(AssetPositionsInfo).filter(AssetPositionsInfo.asset_id == asset_id).delete()
            # 删除资产的合同信息
            session.query(AssetContractsInfo).filter(AssetContractsInfo.asset_id == asset_id).delete()
            # 删除资产的归属信息
            session.query(AssetBelongsInfo).filter(AssetBelongsInfo.asset_id == asset_id).delete()
            # 删除资产的租户信息
            session.query(AssetCustomersInfo).filter(AssetCustomersInfo.asset_id == asset_id).delete()


    @classmethod
    def list_manufacture(cls, manufacture_name=None, page=1, page_size=10, field=None, dir="ascend"):
        # Session = sessionmaker(bind=engine,expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            # 查询厂商表
            query = session.query(AssetManufacturesInfo)
            # 数据库查询参数
            if manufacture_name is not None:
                query = query.filter(AssetManufacturesInfo.name.like('%' + manufacture_name + '%'))

            # 总数
            count = query.count()
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            assert_list = query.all()
            # 返回
            return count, assert_list

    @classmethod
    def create_manufacture(cls, manufacture_info):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(manufacture_info)

    @classmethod
    def delete_manufacture(cls, manufacture_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            # 删除资产的厂商信息
            session.query(AssetManufacturesInfo).filter(AssetManufacturesInfo.id == manufacture_id).delete()

    @classmethod
    def get_manufacture_by_id(cls, manufacture_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.query(AssetManufacturesInfo).filter(AssetManufacturesInfo.id == manufacture_id).first()

    @classmethod
    def get_manufacture_by_name(cls, manufacture_name):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.query(AssetManufacturesInfo).filter(AssetManufacturesInfo.name == manufacture_name).first()


    @classmethod
    def get_manufacture_by_asset_id(cls, asset_id):
        session = get_session()
        with session.begin():
            return session.query(AssetManufacturesInfo).filter(AssetManufacturesInfo.asset_id == asset_id).first()

    @classmethod
    def update_manufacture(cls, manufacture_db):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.merge(manufacture_db)

    @classmethod
    def get_position_by_asset_id(cls, asset_id):
        session = get_session()
        with session.begin():
            return session.query(AssetPositionsInfo).filter(AssetPositionsInfo.asset_id == asset_id).first()

    @classmethod
    def get_contract_by_asset_id(cls, asset_id):
        session = get_session()
        with session.begin():
            return session.query(AssetContractsInfo).filter(AssetContractsInfo.asset_id == asset_id).first()

    @classmethod
    def get_belong_by_asset_id(cls, asset_id):
        session = get_session()
        with session.begin():
            return session.query(AssetBelongsInfo).filter(AssetBelongsInfo.asset_id == asset_id).first()

    @classmethod
    def get_customer_by_asset_id(cls, asset_id):
        session = get_session()
        with session.begin():
            return session.query(AssetCustomersInfo).filter(AssetCustomersInfo.asset_id == asset_id).first()

    @classmethod
    def create_asset_customer(cls, customer_db):
        session = get_session()
        with session.begin():
            return session.merge(customer_db)

    # 资产类型查询列表
    @classmethod
    def list_asset_type(cls, id, parent_id, asset_type_name, asset_type_name_zh):
        # Session = sessionmaker(bind=engine,expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            query = session.query(AssetType)
            # 数据库查询参数
            if id is not None:
                query = query.filter(AssetType.id == id)
            if parent_id is not None:
                query = query.filter(AssetType.parent_id == parent_id)
            if asset_type_name is not None:
                query = query.filter(AssetType.asset_type_name.like('%' + asset_type_name + '%'))
            if asset_type_name_zh is not None:
                query = query.filter(AssetType.asset_type_name_zh.like('%' + asset_type_name_zh + '%'))
            # 默认按照序号排序
            query = query.order_by(AssetType.queue.asc())
            # 查询所有数据
            assert_type_list = query.all()
            # 返回
            return assert_type_list


    @classmethod
    def create_asset_type(cls, asset_type):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(asset_type)


    @classmethod
    def delete_asset_type(cls, asset_type_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            # 删除资产类型信息
            session.query(AssetType).filter(AssetType.id == asset_type_id).delete()

    @classmethod
    def get_asset_type_by_id(cls, asset_type_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.query(AssetType).filter(AssetType.id == asset_type_id).first()

    @classmethod
    def update_asset_type(cls, asset_type_info):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(asset_type_info)

    # 资产配件查询列表
    @classmethod
    def list_asset_part(cls, asset_id=None):
        # Session = sessionmaker(bind=engine,expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            query = session.query(AssetPartsInfo)
            # 数据库查询参数
            if asset_id is not None:
                query = query.filter(AssetPartsInfo.asset_id == asset_id)
            # 查询所有数据
            assert_part_list = query.all()
            # 返回
            return assert_part_list


    @classmethod
    def list_asset_part_page(cls, part_catalog=None, asset_id=None, name=None, page=1, page_size=10, field=None, dir="ascend"):
        # Session = sessionmaker(bind=engine,expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            query = session.query(*part_columns, AssetBasicInfo.name.label("asset_name"), AssetBasicInfo.asset_number.label("asset_number"),
                                  AssetManufacturesInfo.name.label("manufacturer_name"), AssetType.asset_type_name.label("part_type_name"))
            # 外连接
            query = query.outerjoin(AssetBasicInfo, AssetBasicInfo.id == AssetPartsInfo.asset_id). \
                outerjoin(AssetManufacturesInfo, AssetManufacturesInfo.id == AssetPartsInfo.manufacturer_id). \
                outerjoin(AssetType, AssetType.id == AssetPartsInfo.part_type_id)
                # 数据库查询参数
            if name is not None:
                query = query.filter(AssetPartsInfo.name.like('%' + name + '%'))
            if asset_id is not None:
                query = query.filter(AssetPartsInfo.asset_id == asset_id)
            if part_catalog is not None:
                if part_catalog == "inventory":
                    query = query.filter(AssetPartsInfo.asset_id == None)
                if part_catalog == "used":
                    query = query.filter(AssetPartsInfo.asset_id != None)
            # 总数
            count = query.count()
            # 分页条件
            page_size = int(page_size)
            page_num = int(page)
            # 查询所有数据
            if page_size == -1:
                return count, query.all()
            # 页数计算
            start = (page_num - 1) * page_size
            query = query.limit(page_size).offset(start)
            assert_part_list = query.all()
            # 返回
            return count, assert_part_list


    @classmethod
    def create_asset_part(cls, asset_part_info):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(asset_part_info)

    @classmethod
    def update_asset_part(cls, asset_part_info):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(asset_part_info)

    @classmethod
    def delete_asset_part(cls, asset_part_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            # 删除资产的厂商信息
            session.query(AssetPartsInfo).filter(AssetPartsInfo.id == asset_part_id).delete()

    @classmethod
    def delete_asset_part_by_asset_id(cls, asset_id):
        session = get_session()
        with session.begin():
            # 删除资产的厂商信息
            session.query(AssetPartsInfo).filter(AssetPartsInfo.id == asset_id).delete()

    @classmethod
    def get_asset_part_by_id(cls, asset_part_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.query(AssetPartsInfo).filter(AssetPartsInfo.id == asset_part_id).first()


    # 资产流量查询列表
    @classmethod
    def list_asset_flow(cls, asset_id=None, asset_ids=None):
        # Session = sessionmaker(bind=engine,expire_on_commit=False)
        # session = Session()
        session = get_session()
        position_alias1 = aliased(AssetPositionsInfo)
        basic_alias1 = aliased(AssetBasicInfo)
        with session.begin():
            query = session.query(*flow_columns, AssetPositionsInfo.cabinet_position.label("cabinet_position"),AssetPositionsInfo.u_position.label("u_position"),
                                  AssetBasicInfo.name.label("asset_name"),basic_alias1.name.label("opposite_asset_name"),
                                  position_alias1.cabinet_position.label("opposite_cabinet_position"), position_alias1.u_position.label("opposite_u_position"))
            # 外连接
            query = query.outerjoin(AssetPositionsInfo, AssetPositionsInfo.asset_id == AssetFlowsInfo.asset_id). \
                outerjoin(position_alias1, position_alias1.asset_id == AssetFlowsInfo.opposite_asset_id). \
                outerjoin(AssetBasicInfo, AssetBasicInfo.id == AssetFlowsInfo.asset_id). \
                outerjoin(basic_alias1, basic_alias1.id == AssetFlowsInfo.opposite_asset_id)
                    # 数据库查询参数
            if asset_id is not None:
                query = query.filter(AssetFlowsInfo.asset_id == asset_id)
            if asset_ids is not None:
                query = query.filter(AssetFlowsInfo.id.in_(asset_ids.split(',')))
            # 查询所有数据
            assert_flow_list = query.all()
            # 返回
            return assert_flow_list

    @classmethod
    def create_asset_flow(cls, asset_flow):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.add(asset_flow)

    @classmethod
    def delete_asset_flow(cls, asset_flow_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            # 删除网络设备流信息
            session.query(AssetFlowsInfo).filter(AssetFlowsInfo.id == asset_flow_id).delete()

    @classmethod
    def get_asset_flow_by_id(cls, asset_flow_id):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            return session.query(AssetFlowsInfo).filter(AssetFlowsInfo.id == asset_flow_id).first()

    @classmethod
    def update_asset_flow(cls, asset_flow_info):
        # Session = sessionmaker(bind=engine, expire_on_commit=False)
        # session = Session()
        session = get_session()
        with session.begin():
            session.merge(asset_flow_info)

    # 资产流量查询列表
    @classmethod
    def list_asset_column(cls, asset_type=None):
        session = get_session()
        with session.begin():
            query = session.query(AssetExtendsColumnsInfo)
            # 数据库查询参数
            if asset_type is not None:
                query = query.filter(AssetExtendsColumnsInfo.asset_type == asset_type)
            # 排序
            query = query.order_by(AssetExtendsColumnsInfo.queue.asc())
            # 查询所有数据
            assert_flow_list = query.all()
            # 返回
            return assert_flow_list

    @classmethod
    def create_asset_column(cls, asset_column_info):
        session = get_session()
        with session.begin():
            session.add(asset_column_info)

    @classmethod
    def delete_asset_column_by_id(cls, id):
        session = get_session()
        with session.begin():
            # 删除扩展字段信息
            session.query(AssetExtendsColumnsInfo).filter(AssetExtendsColumnsInfo.id == id).delete()

    @classmethod
    def get_asset_column_by_id(cls, id):
        session = get_session()
        with session.begin():
            return session.query(AssetExtendsColumnsInfo).filter(AssetExtendsColumnsInfo.id == id).first()

    @classmethod
    def update_asset_column(cls, asset_column_info):
        session = get_session()
        with session.begin():
            session.merge(asset_column_info)

    @classmethod
    def get_asset_column_max_queue(cls, asset_type):
        session = get_session()
        with session.begin():
            # 查询最大顺序
            query = session.query(func.max(AssetExtendsColumnsInfo.queue))
            # 条件
            if asset_type:
                query = query.filter(AssetExtendsColumnsInfo.asset_type == asset_type)
            # 查询
            return query.scalar()
