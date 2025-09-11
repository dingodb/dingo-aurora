import os
import contextlib
from typing import Optional
from pyroute2 import NetNS
import logging

logger = logging.getLogger(__name__)

class NetNSContext:
    """基于 pyroute2 的网络命名空间上下文管理器"""
    
    def __init__(self, netns_name: Optional[str] = None):
        self.netns_name = netns_name
        self.netns = None
        self.original_netns = None
        
    def __enter__(self):
        if not self.netns_name:
            return self
            
        try:
            # 保存当前网络命名空间

            self.original_netns = NetNS()
            
            # 进入目标网络命名空间
            self.netns = NetNS(self.netns_name)
            
            logger.debug(f"已进入网络命名空间: {self.netns_name}")
            return self
            
        except Exception as e:
            # 清理已创建的对象
            if self.original_netns:
                self.original_netns.close()
            if self.netns:
                self.netns.close()
            raise Exception(f"无法进入网络命名空间 {self.netns_name}: {e}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.netns_name:
            return
            
        # 关闭网络命名空间连接
        try:
            if self.netns:
                self.netns.close()
                logger.debug(f"已关闭网络命名空间连接: {self.netns_name}")
        except Exception as e:
            logger.warning(f"关闭目标网络命名空间时发生错误: {e}")
        
        try:
            if self.original_netns:
                self.original_netns.close()
                logger.debug("已关闭原始网络命名空间连接")
        except Exception as e:
            logger.warning(f"关闭原始网络命名空间时发生错误: {e}")
    
    def execute_in_netns(self, func, *args, **kwargs):
        """
        在网络命名空间中执行函数
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
        """
        if not self.netns:
            # 如果没有指定 netns，直接执行函数
            return func(*args, **kwargs)
        
        # 使用 pyroute2 的网络命名空间上下文执行函数
        with self.netns:
            return func(*args, **kwargs)

@contextlib.contextmanager
def in_netns(netns_name: Optional[str]):
    """网络命名空间上下文管理器的便捷函数"""
    with NetNSContext(netns_name) as ctx:
        yield ctx

def list_netns() -> list:
    """列出系统中所有可用的网络命名空间"""
    try:
        from pyroute2 import netns
        netns_list = set(netns.listnetns())
        # 额外检查 /var/run/netns 目录
        netns_dir = "/var/run/netns"
        if os.path.isdir(netns_dir):
            for name in os.listdir(netns_dir):
                netns_list.add(name)
        if os.path.isdir("/run/netns"):
            for name in os.listdir("/run/netns"):
                netns_list.add(name)
        return list(netns_list)
    except Exception as e:
        logger.error(f"列出网络命名空间时发生错误: {e}")
        return []

def netns_exists(netns_name: str) -> bool:
    """检查指定的网络命名空间是否存在"""
    try:
        available_netns = list_netns()
        return netns_name in available_netns
    except Exception:
        return False

def create_netns(netns_name: str) -> bool:
    """创建新的网络命名空间"""
    try:
        from pyroute2 import netns
        netns.create(netns_name)
        logger.info(f"成功创建网络命名空间: {netns_name}")
        return True
    except Exception as e:
        logger.error(f"创建网络命名空间 {netns_name} 时发生错误: {e}")
        return False

def remove_netns(netns_name: str) -> bool:
    """删除网络命名空间"""
    try:
        from pyroute2 import netns
        netns.remove(netns_name)
        logger.info(f"成功删除网络命名空间: {netns_name}")
        return True
    except Exception as e:
        logger.error(f"删除网络命名空间 {netns_name} 时发生错误: {e}")
        return False