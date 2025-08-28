from enum import Enum


class AiInstanceStatus(Enum):
    """数据库状态枚举"""
    READY = "READY"
    RUNNING = "RUNNING"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    DELETING = "DELETING"
    ERROR = "ERROR"

    @classmethod
    def from_string(cls, value: str):
        """从字符串创建枚举值，忽略大小写"""
        if not value:
            return cls.READY
        try:
            return cls[value.upper()]
        except KeyError:
            return cls.ERROR

class K8sStatus(Enum):
    """Kubernetes Pod 状态枚举"""
    PENDING = "Pending"
    RUNNING = "Running"
    STOPPED = "Stopped"
    ERROR = "Error"

    @classmethod
    def from_string(cls, value: str):
        """从字符串创建枚举值，忽略大小写"""
        if not value:
            return cls.STOPPED
        try:
            return cls[value.upper()]
        except KeyError:
            return cls.ERROR