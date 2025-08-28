import logging
import os
from logging.handlers import RotatingFileHandler

repo_type_http = "http"
repo_type_oci = "oci"
log_level = "INFO"
log_path = "/var/log/dingo-command/"
chart_nubmer = 5
try_times = 3
time_out = 10
repo_time_out = 30
repo_update_time_out = 900
repo_global_name = "zetyun_harbor"
repo_global_cluster_id = "all"
repo_status_create = "creating"
repo_status_success = "available"
repo_status_failed = "failed"
repo_status_stop = "unavailable"
repo_status_sync = "syncing"
repo_status_update = "updating"
repo_status_delete = "deleting"
app_status_create = "creating"
app_status_success = "deployed"
app_status_failed = "failed"
app_status_update = "updating"
app_status_delete = "deleting"
chart_status_success = "available"
chart_status_stop = "unavailable"
helm_cache = "helm"
resource_status_active = "active"
resource_status_success = "succeeded"
resource_status_pend = "pending"
resource_status_failed = "failed"
resource_status_unknown = "unknown"
registry_config = "config.json"
tag_data = {
    1: {"chinese_name": "基础设施", "name": "Infrastructure"},
    2: {"chinese_name": "监控", "name": "Monitor"},
    3: {"chinese_name": "日志", "name": "Log"},
    4: {"chinese_name": "存储", "name": "Storage"},
    5: {"chinese_name": "中间件", "name": "Middleware"},
    6: {"chinese_name": "开发工具", "name": "Development Tools"},
    7: {"chinese_name": "Web应用", "name": "Web Application"},
    8: {"chinese_name": "数据库", "name": "Database"},
    9: {"chinese_name": "安全", "name": "Security"},
    10: {"chinese_name": "大数据", "name": "Big Data"},
    11: {"chinese_name": "AI工具", "name": "AI Tools"},
    12: {"chinese_name": "网络服务", "name": "Network Service"},
    13: {"chinese_name": "其他", "name": "Others"},
}
tag_id_data = {
    "Infrastructure": 1,
    "Monitor": 2,
    "Log": 3,
    "Storage": 4,
    "Middleware": 5,
    "Development Tools": 6,
    "Web Application": 7,
    "Database": 8,
    "Security": 9,
    "Big Data": 10,
    "AI Tools": 11,
    "Network Service": 12,
    "Others": 13,
}

def init_logger(service_name):
    # 确保日志目录存在
    os.makedirs(log_path, exist_ok=True)

    logger = logging.getLogger(service_name)
    if logger.handlers:
        return logger
    logger.setLevel(log_level)

    # 创建专属文件处理器 - 使用RotatingFileHandler实现轮转
    service_name_log = os.path.join(log_path, f"{service_name}.log")

    # 配置轮转策略：50MB/文件，保留5个备份
    handler = RotatingFileHandler(
        service_name_log,
        maxBytes=50 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    handler.setLevel(log_level)

    # 统一日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(pathname)s:%(lineno)d] - %(message)s"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger

ChartLOG = init_logger("chart")