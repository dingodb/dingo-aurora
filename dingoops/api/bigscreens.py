# 大屏的api接口
from fastapi import APIRouter, Query

from dingoops.services.bigscreens import BigScreensService

router = APIRouter()

@router.get("/bigscreen/metrics", summary="获取大屏指标数据")
# TODO: 错误处理
async def get_bigscreen_metrics(name: str, region: str = None):
    return BigScreensService.get_bigscreen_metrics(name, region)


@router.get("/bigscreen/metrics_configs", summary="获取大屏指标配置信息")
# TODO: name 可选参数做筛选
async def list_bigscreen_metrics_configs():
    # 返回数据接口
    try:
        result = BigScreensService.list_bigscreen_metrics_configs()
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

@router.get("/bigscreen/query", summary="获取大屏指标下钻数据", description="metrics format: DCGM_FI_DEV_MEM_CLOCK{Hostname=\"k8s-demo-gpu-11-80\"}")
# 转发给 prometheus, 将查询到的数据返回
async def query_bigscreen_metrics(promql: str):
    metrics = BigScreensService.fetch_metrics_with_promql(promql)
    return metrics

@router.get("/bigscreen/query_range", summary="获取一段时间内的大屏指标下钻数据", description="Time format: YYYY-MM-DD HH:mm:ss")
# 转发给 prometheus, 将查询到的数据返回(query_range 方式)
async def query_range_bigscreen_metrics(promql: str, start_time: str, end_time: str = None, step: str = None):
    metrics = BigScreensService.fetch_metrics_with_promql(promql, query_range=True, start_time=start_time, end_time=end_time, step=step)
    return metrics

