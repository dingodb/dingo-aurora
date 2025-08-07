# 路由接口功能
import os

from fastapi import APIRouter
from dingo_command.api import assets, bigscreens, system, monitor, cluster, node, instance, websocket, resources, \
    message, cloudkitty, aiinstance
from dingo_command.api.k8s import resource

# 启动时创建excel的临时存放目录
excel_temp_dir = "/home/dingo_command/temp_excel/"
os.makedirs(excel_temp_dir, exist_ok=True)

api_router = APIRouter()
api_router.include_router(assets.router, tags=["Assets"])
api_router.include_router(bigscreens.router, tags=["BigScreens"])
api_router.include_router(system.router, tags=["Systems"])
api_router.include_router(monitor.router, tags=["Monitors"])

api_router.include_router(cluster.router, tags=["Cluster"])
api_router.include_router(node.router, tags=["Node"])
api_router.include_router(websocket.router, tags=["WebSockets"])
api_router.include_router(resources.router, tags=["Resources"])
api_router.include_router(instance.router, tags=["Instance"])
api_router.include_router(cloudkitty.router, tags=["CloudKitty"])
api_router.include_router(message.router, tags=["Message"])
api_router.include_router(resource.router, tags=["K8s"])
api_router.include_router(aiinstance.router, tags=["Ai Instance"])

