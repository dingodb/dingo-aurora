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
def install_app_chart(charts:List[CreateAppObject]):
    # 判空
    for chart in charts:
        chart.namespace = "default" if not chart.namespace else chart.namespace
        chart.values = {} if not chart.values else chart.values
    # 调用service库chart.py中的install_app方法
    chart_service = ChartService()
    chart_service.install_app(chart)
    
