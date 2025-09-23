import json
import concurrent.futures
from dingo_command.api.chart import ChartService
from dingo_command.api.k8s.resource import List
from dingo_command.db.models.cluster.models import Taskinfo
from dingo_command.api.model.chart import CreateAppObject
from dingo_command.db.models.cluster.sql import TaskSQL

def update_task_state(task:Taskinfo):
    # 判空
    query_params = {"task_id": task.task_id}
    count, data = TaskSQL.list(query_params)
    if count == 0 or data == []:
        # 如果没有找到对应的任务，则插入
        TaskSQL.insert(task)
        return task.task_id
    else:
        # 如果找到了对应的任务，则更新
        first_task = data[0]  # Get the first task from the result list
        first_task.state = task.state
        first_task.end_time = task.end_time
        first_task.detail = task.detail
        TaskSQL.update(task)
        return task.task_id

# def install_app_chart(charts:List[CreateAppObject], cluster_id):
#     # 判空
#     try:
#         if charts is None or charts == []:
#             return
#         chart_service = ChartService()
#         for chart in charts:
#             chart.cluster_id = cluster_id
#             chart.namespace = "kube-system" if not chart.namespace else chart.namespace
#             # 先获取chart的values
#             res = chart_service.get_chart_version(chart.chart_id, chart.chart_version)
#             if res.get("data").values:
#                 chart.values = json.loads(res.get("data").values)
#             else:
#                 chart.values = {}
#             # 调用service库chart.py中的install_app方法
#             chart_service.install_app(chart)
#     except Exception as e:
#         print(f"install helm chart err: {e}")
#         raise e


def install_single_chart(chart: CreateAppObject, cluster_id: str):
    """
    在线程中执行的单个 Chart 安装任务。
    这个函数被设计为线程安全的，每个任务使用独立的 ChartService 实例。
    """
    chart_service = ChartService()  # 每个线程独立实例，避免线程安全问题
    try:
        # 配置 chart 参数
        chart.cluster_id = cluster_id
        chart.namespace = "kube-system" if not chart.namespace else chart.namespace

        # 获取 chart 的 values
        res = chart_service.get_chart_version(chart.chart_id, chart.chart_version)
        if res.get("data") and res.get("data").values:
            try:
                chart.values = json.loads(res.get("data").values)
            except json.JSONDecodeError:
                chart.values = {}
        else:
            chart.values = {}

        # 调用安装方法
        result = chart_service.install_app(chart)
        return result
    except Exception as exc:
        # 捕获所有异常，记录日志并返回异常信息
        return exc  # 或者返回一个包含错误信息的字典


def install_app_chart(charts: List[CreateAppObject], cluster_id: str, max_workers: int = 10):
    """
    使用多线程并发安装多个 Helm Chart。
    一个任务的失败不会影响其他任务的执行。

    Args:
        charts: 要安装的 Chart 配置列表。
        cluster_id: 集群 ID。
        max_workers: 线程池中最大线程数，控制并发度。
    """
    if not charts:
        return []

    # 用于存储每个任务的未来对象和图表名称的映射
    future_to_chart_name = {}

    # 创建线程池执行器
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务到线程池
        for chart in charts:
            # 为每个图表提交一个任务
            future = executor.submit(install_single_chart, chart, cluster_id)
            future_to_chart_name[future] = chart.name

        # 处理任务结果和异常
        results = []
        for future in concurrent.futures.as_completed(future_to_chart_name):
            try:
                # 获取任务返回结果，这会阻塞直到该任务完成
                result = future.result()
                results.append(result)
                # 如果 install_single_chart 在成功时返回了特定结果，你可以在这里处理
                # 例如，如果它返回了安装状态，你可以记录下来
            except Exception as exc:
                results.append(exc)

    return results