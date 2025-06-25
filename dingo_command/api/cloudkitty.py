# 计费的api接口
import os
from typing import List
from urllib.parse import unquote

from oslo_log import log

from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

from dingo_command.api.model.cloudkitty import CloudKittyRatingSummaryDetail, RatingModuleConfigHashMapMapping, RatingModuleConfigHashMapThreshold, RatingModules
from dingo_command.services.cloudkitty import CloudKittyService
from dingo_command.utils import file_utils

from dingo_command.utils.constant import EXCEL_TEMP_DIR
from dingo_command.utils.datetime import convert_timestamp_to_date, system_time_to_utc
from fastapi import APIRouter, HTTPException, Query

LOG = log.getLogger(__name__)
router = APIRouter()

cloudkitty_service = CloudKittyService()

@router.get("/cloudkitty/download/ratingSummary/execl", summary="下载计费汇总execl表格", description="下载计费汇总execl表格")
async def download_rating_summary_execl(begin: str = Query(None, description="开始时间"),
                                        end: str = Query(None, description="结束时间时间"),
                                        tenant_id: str = Query(None, description="项目ID"),
                                        resource_type: str = Query(None, description="资源类型")):
    # 把数据库中的资产数据导出资产信息数据
    if begin is None or end is None:
        # result_file_name = "rating_detail_all_project_total_time_" + format_d8q_timestamp_without_hyphens() + ".xlsx"
        result_file_name = "rating_detail_all_project_total_time"+ ".xlsx"
    else:
        # result_file_name = "rating_detail_all_project_" + switch_time_to_time(begin, end) + "_" + format_d8q_timestamp_without_hyphens() + ".xlsx"
        result_file_name = "rating_detail_all_project_" + convert_timestamp_to_date(unquote(begin), unquote(end)) + ".xlsx"
    # 导出文件路径
    result_file_path = EXCEL_TEMP_DIR + result_file_name
    # 生成文件
    # 读取excel文件内容
    try:
        # 声明查询条件的dict
        query_params = {}
        if begin:
            query_params['begin'] = system_time_to_utc(unquote(begin))
        if end:
            query_params['end'] = system_time_to_utc(unquote(end))
        if tenant_id:
            query_params['tenant_id'] = tenant_id
        if resource_type:
            query_params['resource_type'] = resource_type
        # 生成文件
        cloudkitty_service.download_rating_summary_excel(result_file_path, query_params)
    except Exception as e:
        import traceback
        traceback.print_exc()
        file_utils.cleanup_temp_file(result_file_path)
        raise HTTPException(status_code=400, detail="generate execl file error")

    # 文件存在则下载
    if os.path.exists(result_file_path):
        return FileResponse(
            path=result_file_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=result_file_name,  # 下载时显示的文件名
            background = BackgroundTask(file_utils.cleanup_temp_file, result_file_path)
        )
    raise HTTPException(status_code=400, detail="Execl file not found")

@router.post("/cloudkitty/download/ratingSummaryDetail/pdf", summary="下载计费汇总详情PDF文件", description="下载计费汇总详情PDF文件")
async def rating_summary_detail_pdf_download(detail: List[CloudKittyRatingSummaryDetail],
                                             language: str = Query(None, description="当前环境语言")):

    # 生成计费汇总租户详情数据
    temp_data, tenant_id_and_name_period = cloudkitty_service.generate_rating_summary_detail_data(detail, language)
    if temp_data is None:
        return

    # result_file_pdf_name = "rating_summary_" + tenant_id_and_name_period + "_" + format_d8q_timestamp_without_hyphens() + ".pdf"
    result_file_pdf_name = "rating_summary_" + tenant_id_and_name_period + ".pdf"
    # 导出文件路径
    result_file_pdf_path = EXCEL_TEMP_DIR + result_file_pdf_name

    # 1. 生成PDF文件
    try:
        cloudkitty_service.generate_rating_summary_detail_pdf(result_file_pdf_path, temp_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        file_utils.cleanup_temp_file(result_file_pdf_path)
        raise HTTPException(status_code=400, detail="generate pdf file error")

    if not os.path.exists(result_file_pdf_path):
        raise HTTPException(status_code=404, detail="PDf file not found")

    def file_stream():
        with open(result_file_pdf_path, "rb") as f:
            while chunk := f.read(8192):  # 8KB分块读取
                yield chunk
        file_utils.cleanup_temp_file(result_file_pdf_path)

    return StreamingResponse(
        file_stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={result_file_pdf_name}"}
    )

@router.put("/cloudkitty/module_config/hashmap/mappings/{mapping_id}", summary="编辑计费映射哈希字段或服务映射",description="编辑计费映射哈希字段或服务映射")
async def edit_rating_module_config_hashmap_mappings(mapping_id: str, mapping: RatingModuleConfigHashMapMapping):
    try:
        return cloudkitty_service.edit_rating_module_config_hashmap_mappings(mapping_id, mapping)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail={e})

@router.put("/cloudkitty/module_config/hashmap/thresholds/{threshold_id}", summary="编辑计费映射哈希服务阈值",description="编辑计费映射哈希服务阈值")
async def edit_rating_module_config_hashmap_thresholdings(threshold_id: str, thresholding: RatingModuleConfigHashMapThreshold):
    try:
        return cloudkitty_service.edit_rating_module_config_hashmap_thresholdings(threshold_id, thresholding)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail={e})

@router.put("/cloudkitty/modules/{module_id}", summary="编辑计费模型（禁用/启用模块、优先级）",description="编辑计费模型（禁用/启用模块、优先级）")
async def edit_rating_module_modules(module_id: str, modules: RatingModules):
    try:
        return cloudkitty_service.edit_rating_module_modules(module_id, modules)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail={e})



