import os
import ctypes
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


# def enter_netns(netns):
#     """
#     切换当前进程到指定的网络命名空间。
    
#     :param namespace: netns名称，例如 'myns'
#     """
#     netns_path = f"/var/run/netns/{netns}"
#     if not os.path.exists(netns_path):
#         raise FileNotFoundError(f"Netns '{netns}' 不存在。确保已创建。")
    
#     # 打开netns文件描述符
#     fd = os.open(netns_path, os.O_RDONLY)
    
#     # 加载libc并调用setns
#     libc = ctypes.CDLL('libc.so.6')
#     if libc.setns(fd, CLONE_NEWNET) != 0:
#         raise OSError("切换netns失败。请检查权限（需root）。")
    
#     os.close(fd)
#     print(f"已切换到netns: {namespace}")

def run_playbook(playbook_name, inventory, data_dir, ssh_key, extravars=None, limit=None, netns=None):
    # 设置环境变量
    envvars = {
        "ANSIBLE_FORKS": 10,
        "ANSIBLE_BECOME": "True",
        "CURRENT_DIR": inventory,
    }
    # 如果指定了 netns，则修改环境变量
    if netns and netns != "":
        # Create the netns_ssh.sh script
        script_path = os.path.join(data_dir, "netns_ssh.sh")
        with open(script_path, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f"/usr/sbin/ip netns exec {netns} ssh \"$@\"\n")
        os.chmod(script_path, 0o755)
        envvars["ANSIBLE_SSH_EXECUTABLE"] = script_path
    
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