# 资产的api接口
import os
import time
from io import BytesIO
from typing import List

import pandas
from fastapi import APIRouter, UploadFile, File, Query, Path, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, Response
from mako.testing.helpers import result_lines

from api.model.assets import AssetCreateApiModel, AssetManufacturerApiModel, AssetUpdateStatusApiModel, \
    AssetPartApiModel, AssetTypeApiModel, AssetFlowApiModel, AssetBatchDownloadApiModel, AssetBatchUpdateApiModel, \
    AssetExtendColumnApiModel
from api.model.system import OperateLogApiModel
from api.response import ResponseModel, success_response
from services.assets import AssetsService
from services.system import SystemService
from utils.constant import EXCEL_TEMP_DIR, ASSET_TEMPLATE_ASSET_SHEET, ASSET_TEMPLATE_PART_SHEET, \
    ASSET_TEMPLATE_ASSET_TYPE, ASSET_TEMPLATE_NETWORK_SHEET
from utils.datetime import format_unix_timestamp, format_d8q_timestamp
from oslo_log import log
import io

LOG = log.getLogger(__name__)

router = APIRouter()
assert_service = AssetsService()
system_service = SystemService()

# 以下是资产-网络设备的流表信息的类型相关的接口 start
@router.get("/assets/flows", summary="查询资产网络设备流信息列表", description="根据各种条件查询资产网络设备流信息列表")
async def list_assets_flows(
        asset_id:str = Query(None, description="资产id")):
    # 接收查询参数
    # 返回数据接口
    try:
        # 查询成功
        result = assert_service.list_assets_flows(asset_id, None)
        return result
    except Exception as e:
        return None

@router.post("/assets/flows", summary="创建网络设备的流转数据", description="创建网络设备的流转数据")
async def create_asset_flow(asset_flow:AssetFlowApiModel):
    # 创建资产类型
    try:
        # 创建成功
        result = assert_service.create_asset_flow(asset_flow)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="create", resource_type="flow", resource_id=result, resource_name=asset_flow.label, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset flow create error")

@router.delete("/assets/flows/{id}", summary="删除网络设备的流转数据", description="根据资产id删除网络设备的流转数据")
async def delete_asset_flow_by_id(id:str):
    # 删除资产类型
    try:
        # 删除成功
        result = assert_service.delete_asset_flow_by_id(id)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="update", resource_type="flow", resource_id=result, resource_name=id, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset flow delete error")

@router.put("/assets/flows/{id}", summary="更新网络设备的流转数据", description="根据id更新网络设备的流转数据")
async def update_asset_flow_by_id(id:str, asset_flow:AssetFlowApiModel):
    # 更新资产类型
    try:
        # 更新成功
        result = assert_service.update_asset_flow_by_id(id, asset_flow)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset flow update error")


# 以上是资产-网络设备的流表信息的类型相关的接口 end

# 以下是扩展字段的相关接口 start
@router.get("/assets/columns", summary="查询资产的扩展字段列表", description="根据各种条件查询资产扩展字段信息列表")
async def list_assets_columns(
        asset_type:str = Query(None, description="资产类型")):
    # 返回数据接口
    try:
        # 查询成功
        result = assert_service.list_assets_columns(asset_type)
        return result
    except Exception as e:
        return None

@router.post("/assets/columns", summary="创建扩展字段", description="根据输入信息创建扩展字段数据")
async def create_assets_columns(asset_column:AssetExtendColumnApiModel):
    # 创建扩展字段
    try:
        # 调用创建接口
        result = assert_service.create_asset_column(asset_column)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="create", resource_type="column", resource_id=result, resource_name=asset_column.column_name, operate_flag=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset column create error")

@router.delete("/assets/columns/{id}", summary="删除扩展字段", description="根据id删除扩展字段")
async def delete_asset_column_by_id(id:str):
    # 删除扩展字段
    try:
        # 删除成功
        result = assert_service.delete_asset_column_by_id(id)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="delete", resource_type="column", resource_id=result, resource_name=id, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset extend column delete error")

@router.put("/assets/columns/{id}", summary="更新扩展字段信息", description="根据id更新扩展字段信息")
async def update_asset_column_by_id(id:str, asset_column:AssetExtendColumnApiModel):
    # 更新资产类型
    try:
        # 更新成功
        result = assert_service.update_asset_column_by_id(id, asset_column)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="update", resource_type="column", resource_id=id, resource_name=id, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset extend column update error")
# 以上是扩展字段的相关接口 end

# 以下是资产的类型相关的接口 start

@router.get("/assets/types", summary="查询资产类型列表", description="根据各种条件查询资产列表数据")
async def list_assets_types(
        id:str = Query(None, description="资产类型id"),
        asset_type_name:str = Query(None, description="资产类型名称"),
        asset_type_name_zh:str = Query(None, description="资产类型中文名称")):
    # 接收查询参数
    # 返回数据接口
    try:
        # 查询成功
        result = assert_service.list_assets_types(id, asset_type_name, asset_type_name_zh, True)
        return result
    except Exception as e:
        return None

@router.post("/assets/types", summary="创建资产类型", description="创建资产类型信息")
async def create_asset_type(asset_type:AssetTypeApiModel):
    # 创建资产类型
    try:
        # 创建成功
        result = assert_service.create_asset_type(asset_type)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="create", resource_type="asset_type", resource_id=result, resource_name=asset_type.asset_type_name_zh, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset type create error")

@router.delete("/assets/types/{id}", summary="删除资产类型", description="根据资产id删除资产类型信息(默认删掉子类型)")
async def delete_asset_type_by_id(id:str):
    # 删除资产类型
    try:
        # 删除成功
        result = assert_service.delete_asset_type_by_id(id)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="delete", resource_type="asset_type", resource_id=id, resource_name=id, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset type delete error")

@router.put("/assets/types/{id}", summary="更新资产类型信息", description="根据id更新资产类型信息")
async def update_asset_type_by_id(id:str, asset_type:AssetTypeApiModel):
    # 更新资产类型
    try:
        # 更新成功
        result = assert_service.update_asset_type_by_id(id, asset_type)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="update", resource_type="asset_type", resource_id=id, resource_name=asset_type.asset_type_name_zh, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset type update error")

# 以下是资产的类型相关的接口 end

@router.get("/assets/download", summary="下载资产信息", description="根据不同类型下载对应的资产文件")
async def download_assets_xlsx(asset_type: str):
    # 类型是空
    if asset_type is None or len(asset_type) <= 0:
        return None
    # 把数据库中的资产数据导出资产信息数据
    result_file_name = "asset_" + format_d8q_timestamp() + ".xlsx"
    # 导出文件路径
    result_file_path = EXCEL_TEMP_DIR + result_file_name
    # 生成文件
    # 读取excel文件内容
    try:
        # 生成文件
        assert_service.create_asset_excel(asset_type, result_file_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
    # 文件存在则下载
    if os.path.exists(result_file_path):
        return FileResponse(
            path=result_file_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=result_file_name  # 下载时显示的文件名
        )
    return {"error": "File not found"}

@router.post("/assets/download", summary="批量下载指定资产信息", description="根据选择好的数据下载对应的资产文件")
async def download_assets_xlsx_4select(item:AssetBatchDownloadApiModel):
    # 把选中的id的字符串数据库中的资产数据导出资产信息数据
    result_file_name = "asset_" + format_d8q_timestamp() + ".xlsx"
    # 导出文件路径
    result_file_path = EXCEL_TEMP_DIR + result_file_name
    # 生成文件
    # 读取excel文件内容
    try:
        if item is None or item.asset_type is None or item.asset_ids is None:
            raise Exception
        # 生成文件
        assert_service.create_asset_excel_4batch(item, result_file_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
    # 文件存在则下载
    if os.path.exists(result_file_path):
        # 打开文件并读取内容
        file_stream = io.BytesIO()
        with open(result_file_path, "rb") as f:
            hex_content = f.read()
            # print(hex_content)
            file_stream.write(hex_content)
            file_stream.seek(0)  # 重置指针以便后续读取
        # 设置响应头和文件名
        headers = {
            'Content-Disposition': f'attachment; filename="{result_file_name}"'
        }
        # 返回文件流
        return StreamingResponse(file_stream, headers=headers, media_type='application/octet-stream')
        # return FileResponse(
        #         path=result_file_path,
        #         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        #         filename=result_file_name  # 下载时显示的文件名
        #     )
    return {"error": "File not found"}


# @router.get("/assets", response_model=ResponseModel[dict])
@router.get("/assets", summary="查询资产列表", description="根据各种条件分页查询资产列表数据")
async def list_assets(
        asset_id:str = Query(None, description="资产id"),
        asset_name:str = Query(None, description="资产名称"),
        asset_category:str = Query(None, description="资产大类（服务器、网络设备）"),
        asset_type:str = Query(None, description="资产类型"),
        asset_status:str = Query(None, description="资产状态"),
        frame_position:str = Query(None, description="机架"),
        cabinet_position:str = Query(None, description="机柜"),
        u_position:str = Query(None, description="u位"),
        equipment_number:str = Query(None, description="设备型号"),
        asset_number:str = Query(None, description="资产编号"),
        sn_number:str = Query(None, description="序列号"),
        department_name:str = Query(None, description="部门"),
        user_name:str = Query(None, description="负责人"),
        host_name:str = Query(None, description="主机名称"),
        asset_manufacture_name:str = Query(None, description="厂商名称"),
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys:str = Query(None, description="排序字段"),
        sort_dirs:str = Query(None, description="排序方式"),):
    # 接收查询参数
    # 返回数据接口
    try:
        # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if asset_id:
            query_params['asset_id'] = asset_id
        if asset_name:
            query_params['asset_name'] = asset_name
        if asset_category:
            query_params['asset_category'] = asset_category
        if asset_type:
            query_params['asset_type'] = asset_type
        if asset_status:
            query_params['asset_status'] = asset_status
        if frame_position:
            query_params['frame_position'] = frame_position
        if cabinet_position:
            query_params['cabinet_position'] = cabinet_position
        if u_position:
            query_params['u_position'] = u_position
        if equipment_number:
            query_params['equipment_number'] = equipment_number
        if asset_number:
            query_params['asset_number'] = asset_number
        if sn_number:
            query_params['sn_number'] = sn_number
        if department_name:
            query_params['department_name'] = department_name
        if user_name:
            query_params['user_name'] = user_name
        if host_name:
            query_params['host_name'] = host_name
        if host_name:
            query_params['host_name'] = host_name
        # 查询成功
        result = assert_service.list_assets(query_params, page, page_size, sort_keys, sort_dirs)
        return result
        # return success_response(result)
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset not found")

@router.get("/assets/{asset_id}", summary="查询资产详情", description="根据id查询资产详情数据")
async def get_asset_by_id(asset_id:str,):
    # 返回数据接口
    try:
        # 查询成功
        result = assert_service.get_asset_by_id(asset_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset not found")

@router.delete("/assets/{asset_id}", summary="删除资产", description="根据资产id删除资产信息")
async def delete_asset_by_id(asset_id:str):
    # 创建资产设备
    try:
        # 创建成功
        result = assert_service.delete_asset(asset_id)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="delete", resource_type="asset", resource_id=asset_id, resource_name=asset_id, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset delete error")


@router.put("/assets/{asset_id}", summary="更新资产信息", description="根据资产id更新资产信息")
async def update_asset_by_id(asset_id:str, asset:AssetCreateApiModel):
    # 创建资产设备
    try:
        # 创建成功
        result = assert_service.update_asset(asset_id, asset)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="update", resource_type="asset", resource_id=asset_id, resource_name=asset.asset_name, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None


@router.post("/assets", summary="创建资产", description="创建资产信息")
async def create_asset(asset:AssetCreateApiModel):
    # 创建资产设备
    try:
        # 创建成功
        result = assert_service.create_asset(asset)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="create", resource_type="asset", resource_id=result, resource_name=asset.asset_name, operate_flag=True))
        return result
        # return success_response(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset create error")


@router.post("/assets/update_basic", summary="批量更新资产信息", description="批量更新资产信息")
async def update_asset_batch(asset_batch:AssetBatchUpdateApiModel):
    # 更新资产设备
    try:
        # 修改成功
        result = assert_service.update_asset_list(asset_batch)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset update error")


@router.post("/assets/update_status", summary="批量更新状态", description="批量更新状态")
async def update_assets_status(asset:List[AssetUpdateStatusApiModel]):
    # 更新资产设备的状态
    try:
        # 更新成功
        result = assert_service.update_assets_status(asset)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset update status error")


@router.get("/assets/templates/{template_id}", summary="下载模板", description="根据模板的id下载对应的模板文件")
async def download_asset_template_xlsx(template_id:str):
    # 当前目录
    print(os.getcwd())
    # 模板文件目录绝对路径
    file_dir_path = os.getcwd() + "/api/template/"
    # 模板文件路径
    file_path = file_dir_path + template_id + ".xlsx"
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=template_id + ".xlsx"  # 下载时显示的文件名
        )
    return {"error": "File not found"}


@router.post("/assets/upload/{asset_type}", summary="上传资产文件", description="上传资产文件创建对应数据")
async def upload_asset_xlsx(asset_type: str, file: UploadFile = File(...)):
    # 按照资产模板导入数据
    try:
        # 资产的类型不能为空
        if not asset_type:
            LOG.error("asset type name exist")
            raise Exception
        # 位置
        if asset_type not in ASSET_TEMPLATE_ASSET_TYPE:
            LOG.error("asset type is incompatible")
            raise Exception
        # 文件是否是excel
        if not file.filename.endswith('.xlsx'):
            LOG.error("file suffix is xlsx")
            raise Exception
        # 文件大小
        if file.size > 1024 * 1024 * 5:
            LOG.error("The file size cannot exceed 5MB!")
            raise Exception
        # 读取资产的数据
        contents = await file.read()
        buffer = BytesIO(contents)
        # 服务器类型
        if asset_type == "server":
            # 1、资产设备sheet
            df = pandas.read_excel(buffer, sheet_name=ASSET_TEMPLATE_ASSET_SHEET)
            # 遍历
            for _, row in df.iterrows():
                # 存入一行
                assert_service.import_asset(row)
            # 2、资产设备sheet
            df = pandas.read_excel(buffer, sheet_name=ASSET_TEMPLATE_PART_SHEET)
            # 遍历
            for _, row in df.iterrows():
                # 存入一行
                assert_service.import_asset_part(row)
        elif asset_type == "network":
            # 1、网络设备sheet
            df = pandas.read_excel(buffer, sheet_name=ASSET_TEMPLATE_NETWORK_SHEET)
            # 遍历
            for _, row in df.iterrows():
                # 存入一行
                assert_service.import_asset_network(row)
        elif asset_type == "network_flow":
            # 1、网络设备流sheet
            df = pandas.read_excel(buffer, sheet_name=ASSET_TEMPLATE_NETWORK_SHEET)
            # 遍历
            for _, row in df.iterrows():
                # 存入一行
                assert_service.import_asset_network_flow(row)
        else:
            pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="asset upload error")




# 以下是厂商的相关接口信息
@router.post("/manufactures", summary="创建厂商", description="创建厂商数据信息")
async def create_manufacture(manufacture:AssetManufacturerApiModel):
    # 创建资产设备
    try:
        # 创建成功
        result = assert_service.create_manufacture(manufacture)
        # 记录操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="create", resource_type="manufacture", resource_id=result, resource_name=manufacture.name, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

@router.get("/manufactures", summary="查询厂商", description="根据条件查询厂商分页列表信息")
async def list_manufactures(
        manufacture_name:str = None,
        page: int = 1,
        page_size: int = 10,
        sort_keys:str = None,
        sort_dirs:str = None,):
    # 返回数据接口
    try:
        # 查询成功
        result = assert_service.list_manufactures(manufacture_name, page, page_size, sort_keys, sort_dirs)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="manufacture list error")

@router.delete("/manufactures/{manufacture_id}", summary="删除厂商", description="根据厂商id删除厂商数据信息")
async def delete_manufacture_by_id(manufacture_id:str):
    # 删除厂商
    try:
        # 删除成功
        result = assert_service.delete_manufacture(manufacture_id)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="delete", resource_type="manufacture", resource_id=manufacture_id, resource_name=manufacture_id, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="manufacture delete error")


@router.put("/manufactures/{manufacture_id}", summary="修改厂商", description="修改厂商的数据信息")
async def update_manufacture_by_id(manufacture_id:str, manufacture:AssetManufacturerApiModel):
    # 修改指定id的厂商信息
    try:
        # 修改成功
        result = assert_service.update_manufacture(manufacture_id, manufacture)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="update", resource_type="manufacture", resource_id=manufacture_id, resource_name=manufacture.name, operate_flag=True))
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="manufacture update error")


# 以下时资产配件的相关接口 start
@router.get("/parts", summary="查询资产配件列表", description="根据各种条件分页查询资产配件列表数据")
async def list_assets_parts(
        part_catalog: str = Query(None, description="配件分类：库存配件(inventory)、已用配件(used)"),
        asset_id: str = Query(None, description="资产id"),
        name: str = Query(None, description="配件名称"),
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys: str = Query(None, description="排序字段"),
        sort_dirs: str = Query(None, description="排序方式"),):
    # 返回数据接口
    try:
        # 查询成功
        result = assert_service.list_assets_parts_pages(part_catalog, asset_id, name, page, page_size, sort_keys, sort_dirs)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset part not found")


@router.post("/parts", summary="创建配件", description="根据输入信息创建配件数据")
async def create_assets_parts(asset_part:AssetPartApiModel):
    # 创建配件
    try:
        # 调用创建接口
        result = assert_service.create_asset_part(asset_part)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="create", resource_type="part", resource_id=result, resource_name=asset_part.name, operate_flag=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset part not found")


@router.put("/parts/{id}", summary="修改配件", description="根据id信息修改配件数据")
async def update_asset_part_by_id(id:str, asset_part:AssetPartApiModel):
    # 修改配件
    try:
        # 调用修改接口
        result = assert_service.update_asset_part_by_id(id, asset_part)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="update", resource_type="part", resource_id=id, resource_name=asset_part.name, operate_flag=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset part update error")


@router.delete("/parts/{id}", summary="删除配件", description="根据输入配件的id删除配件数据")
async def delete_asset_part_by_id(id:str):
    # 删除配件
    try:
        # 调用删除接口
        result = assert_service.delete_asset_part_by_id(id)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="delete", resource_type="part", resource_id=id, resource_name=id, operate_flag=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset part delete error")

@router.put("/parts/{id}/bind/{asset_id}", summary="配件绑定资产", description="根据id信息修改配件绑定关系")
async def bind_asset_part_by_id(id:str, asset_id:str):
    # 修改配件
    try:
        # 调用修改接口
        result = assert_service.bind_asset_part_by_id(id, asset_id)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="bind", resource_type="part", resource_id=id, resource_name=id, operate_flag=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset part update error")

@router.put("/parts/{id}/unbind/{asset_id}", summary="配件解绑绑定资产", description="根据id信息修改配件绑定关系")
async def unbind_asset_part_by_id(id:str, asset_id:str):
    # 修改配件
    try:
        # 调用修改接口
        result = assert_service.unbind_asset_part_by_id(id, asset_id)
        # 操作日志
        system_service.create_system_log(OperateLogApiModel(operate_type="unbind", resource_type="part", resource_id=id, resource_name=id, operate_flag=True))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="asset part update error")