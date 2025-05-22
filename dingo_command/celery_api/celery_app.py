import os
from typing import List

from celery import Celery
from sqlalchemy.exc import OperationalError

from dingo_command.celery_api import CONF

# redis的配置信息
REDIS_HOST = CONF.redis.redis_ip
REDIS_PORT = CONF.redis.redis_port
REDIS_PASSWORD = CONF.redis.redis_password
SENTINEL_URL = CONF.redis.sentinel_url

class Config:
    """
    https://docs.celeryproject.org/en/latest/userguide/configuration.html#configuration-and-defaults
    """

    task_acks_late = (
        True  # guarantee task completion but the task may be executed twice
    )
    # if the worker crashes mid execution
    result_expires = 600  # A built-in periodic task will delete the results after this time (seconds)
    # assuming that celery beat is enabled. The task runs daily at 4am.
    # task_ignore_result = True  # now we control this per task
    task_compression = "json"
    result_compression = "json"
    broker_connection_retry = True
    broker_connection_retry_on_startup = True


def get_task_packages(path: str) -> List[str]:
    result = []
    for dirpath, dirnames, filenames in os.walk(path):
        for name in filenames:
            if "__" not in dirpath:  # exclude __pycache__a
                result.append(
                    os.path.join(dirpath, name.split(".")[0])
                    .replace("/", ".")
                    .replace("\\", ".")
                )
    return result


try:
    celery_app = Celery(
        "celery",
        #backend=f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
        backend=SENTINEL_URL,
        broker=SENTINEL_URL,
        #broker="sentinel://:HVvdRCDnbXWVLEgDtVohlQRzDvs2NduPVNqVokr9@10.220.56.4:26379;sentinel://admin:HVvdRCDnbXWVLEgDtVohlQRzDvs2NduPVNqVokr9@10.220.56.5:26379;sentinel://admin:HVvdRCDnbXWVLEgDtVohlQRzDvs2NduPVNqVokr9@10.220.56.6:26379",

        include=get_task_packages(os.path.join("dingo_command", "tasks")),
    )
    celery_app.conf.broker_transport_options = { 'master_name': "kolla" }
    celery_app.conf.result_backend_transport_options = {'master_name': "kolla"}

    celery_app.config_from_object(Config)
    celery_app.connection().ensure_connection(max_retries=3, timeout=15)
except OperationalError as e:
    raise RuntimeError(
        f"Connection to @{REDIS_HOST}:{REDIS_PORT} broker refused."
    ) from e


celery_app.conf.task_default_queue = "main-queue"


if __name__ == "__main__":
    celery_app.worker_main()