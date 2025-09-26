# Copyright 2022 99cloud
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import multiprocessing
import logging
import os

# 设置环境变量以控制 Kubernetes 客户端日志级别
os.environ['KUBERNETES_CLIENT_LOG_LEVEL'] = 'WARNING'

# 关闭 Kubernetes 客户端的详细日志输出
logging.getLogger('kubernetes.client').setLevel(logging.WARNING)
logging.getLogger('kubernetes.client.rest').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('urllib3.util.retry').setLevel(logging.WARNING)

bind = "0.0.0.0:8887"
workers = min(multiprocessing.cpu_count() * 2, 8)  # 平衡性能与资源
timeout = 600                                      # 充足的操作时间  
keepalive = 30                                     # 优化连接复用
proc_name = "dingo-command"
max_requests = 2000       # K8s操作较重，适当提高以减少重启频率
max_requests_jitter = 200 # 增加随机性，避免所有worker同时重启
preload_app = True       # 预加载应用，共享K8s客户端初始化开销

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "root": {"level": "DEBUG", "handlers": ["console"]},
    "loggers": {
        "gunicorn.error": {
            "level": "DEBUG",
            "handlers": ["error_file"],
            "propagate": 0,
            "qualname": "gunicorn_error",
        },
        "gunicorn.access": {
            "level": "DEBUG",
            "handlers": ["access_file"],
            "propagate": 0,
            "qualname": "access",
        },
    },
    "handlers": {
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "generic",
            "filename": "/var/log/dingo-command/dingo-command-error.log",
        },
        "access_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "generic",
            "filename": "/var/log/dingo-command/dingo-command-access.log",
        },
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "generic",
        },
    },
    "formatters": {
        "generic": {
            "format": "%(asctime)s.%(msecs)03d %(process)d %(levelname)s [-] %(message)s",
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter",
        }
    },
}
