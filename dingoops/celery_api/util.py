
from dingoops.db.models.cluster.models import Taskinfo
from dingoops.db.models.cluster.sql import ClusterSQL, TaskSQL

def update_task_state(task:Taskinfo):
    # 判空
    t = TaskSQL.list(task.task_id, task.msg)
    if not t:
      # 如果没有找到对应的任务，则插入
      TaskSQL.insert(task)
      return task.task_id
    else:
      # 如果找到了对应的任务，则更新
      first_task = t[1]  # Get the first task from the result list
      task.id = first_task[0].id
      task.msg = first_task[0].msg
      task.start_time = first_task[0].start_time
      TaskSQL.update(task)
      return task.task_id