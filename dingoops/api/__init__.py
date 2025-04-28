# 路由接口功能
import os

from fastapi import APIRouter
from dingoops.api import assets, bigscreens, system, monitor, cluster, node,websocket, resources


# 启动时创建excel的临时存放目录
excel_temp_dir = "/home/dingoops/temp_excel/"
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
