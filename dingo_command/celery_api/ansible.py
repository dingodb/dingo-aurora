import os
import ansible_runner
from ansible.plugins.callback import CallbackBase

class CustomCallback(CallbackBase):
    def __init__(self):
        super(CustomCallback, self).__init__()
        self.task_results = []

    def v2_runner_on_ok(self, result):
        task_name = result._task.get_name()
        self.task_results.append({"task": task_name, "status": "ok", "result": result._result})

    def v2_runner_on_failed(self, result, ignore_errors=False):
        task_name = result._task.get_name()
        self.task_results.append({"task": task_name, "status": "failed", "result": result._result})

    def v2_runner_on_skipped(self, result):
        task_name = result._task.get_name()
        self.task_results.append({"task": task_name, "status": "skipped", "result": result._result})

    def v2_runner_on_unreachable(self, result):
        task_name = result._task.get_name()
        self.task_results.append({"task": task_name, "status": "unreachable", "result": result._result})



def run_playbook(playbook_name, inventory, data_dir, ssh_key, extravars=None, limit=None):
    # 设置环境变量
    envvars = {
        "ANSIBLE_FORKS": 10,
        "ANSIBLE_BECOME": "True",
        "CURRENT_DIR": inventory,
    }
    inventory_file = os.path.join(inventory, "hosts")
    # 运行 Ansible playbook 异步
    thread, runner = ansible_runner.run_async(
        private_data_dir=data_dir,
        playbook=playbook_name,
        inventory=inventory_file,
        quiet=True,
        envvars=envvars,
        extravars=extravars,
        ssh_key=ssh_key,
        limit=limit,
        forks=50,
    )

    return thread,runner