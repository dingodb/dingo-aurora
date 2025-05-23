# 资源的api接口
import os
from fastapi.responses import FileResponse
from dingo_command.services.cloudkitty import CloudKittyService
from dingo_command.utils.constant import EXCEL_TEMP_DIR
from dingo_command.utils.datetime import format_d8q_timestamp
from fastapi import APIRouter

router = APIRouter()

cloudkitty_service = CloudKittyService()

@router.get("/cloudkitty/download/rating_summary/execl", summary="下载计费汇总execl表格", description="下载计费汇总execl表格")
async def download_rating_summary_execl():
    # 把数据库中的资产数据导出资产信息数据
    result_file_name = "rating_summary_" + format_d8q_timestamp() + ".xlsx"
    # 导出文件路径
    result_file_path = EXCEL_TEMP_DIR + result_file_name
    # 生成文件
    # 读取excel文件内容
    try:
        # 生成文件
        cloudkitty_service.download_rating_summary_excel(result_file_path)
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

@router.post("/cloudkitty/download/rating_summary_detail/pdf", summary="下载计费汇总详情PDF", description="下载计费汇总详情PDF")
async def download_rating_summary_detail_pdf():
    # 把数据库中的资产数据导出资产信息数据
    result_file_name = "rating_summary_detail" + format_d8q_timestamp() + ".pdf"
    # 导出文件路径
    result_file_path = EXCEL_TEMP_DIR + result_file_name
    # 生成文件
    # 读取excel文件内容
    try:
        # 生成文件
        cloudkitty_service.download_rating_summary_excel(result_file_path)
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

