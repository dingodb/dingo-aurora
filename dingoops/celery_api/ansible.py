import time
import ansible_runner

def run_playbook(playbook_name, inventory, data_dir, extravars=None):
    # 设置环境变量
    envvars = {
        "ANSIBLE_FORKS": 1,
    }

    # 运行 Ansible playbook 异步
    thread,runner = ansible_runner.run_async(
        private_data_dir=data_dir,
        playbook=playbook_name,
        inventory=inventory,
        quiet=True,
        envvars=envvars,
        extravars=extravars
    )

    # 处理并打印事件日志
    while runner.status not in ['canceled', 'successful', 'timeout', 'failed']:
        time.sleep(0.01)
        continue

    print("out: {}".format(runner.stdout.read()))
    print("err: {}".format(runner.stderr.read()))
    print(runner.stdout)
    # 等待线程完成
    thread.join()

    # 检查最终状态
    if runner.rc != 0:
        raise Exception(f"Playbook execution failed: {runner.rc}")
    return thread,runner