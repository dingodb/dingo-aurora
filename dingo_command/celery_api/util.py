from dingo_command.db.models.cluster.models import Taskinfo
from dingo_command.db.models.cluster.sql import TaskSQL

def update_task_state(task:Taskinfo):
    # 判空
    count,data = TaskSQL.list(task.task_id, task.msg)
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