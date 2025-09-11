import json
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

def install_app_chart(charts:List[CreateAppObject], cluster_id):
    # 判空
    try:
        if charts is None or charts == []:
            return
        chart_service = ChartService()
        for chart in charts:
            chart.cluster_id = cluster_id
            chart.namespace = "kube-system" if not chart.namespace else chart.namespace
            # 先获取chart的values
            res = chart_service.get_chart_version(chart.chart_id, chart.chart_version)
            if res.get("data").values:
                chart.values = json.loads(res.get("data").values)
            else:
                chart.values = {}
            # 调用service库chart.py中的install_app方法
            chart_service.install_app(chart)
    except Exception as e:
        print(f"install helm chart err: {e}")
        raise e
    
