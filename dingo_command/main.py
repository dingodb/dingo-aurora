from contextlib import asynccontextmanager

from fastapi import FastAPI

from dingo_command.api import api_router
from dingo_command.jobs import (bigscreen_metrics_syncer, asset_resource_relation_syncer,
                                rabbitmq_config_init, instance_status_syncer, cluster_status_syncer, ai_instance_syncer,
                                ai_k8s_node_resource_syncer, chart_app_status_syncer)

PROJECT_NAME = "dingo-command"

app = FastAPI(
    title=PROJECT_NAME,
    openapi_url="/v1/openapi.json",
)

@app.get("/", description="根url")
async def root():
    return {"message": "Welcome to the dingo-command!"}

@app.get("/v1", description="版本号url")
async def root():
    return {"message": "Welcome to the dingo-command of version v1!"}

app.include_router(api_router, prefix="/v1")

# @app.on_event("startup")
# async def app_start():
#     bigscreen_metrics_syncer.start()

@asynccontextmanager
async def lifespan(app: FastAPI):
    bigscreen_metrics_syncer.start()
    asset_resource_relation_syncer.start()
    rabbitmq_config_init.start()
    instance_status_syncer.start()
    cluster_status_syncer.start()
    ai_instance_syncer.start()
    ai_k8s_node_resource_syncer.start()
    chart_app_status_syncer.start()
    yield
    # Add any shutdown logic here if needed

app.router.lifespan_context = lifespan

# 本地启动作测试使用
if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", reload=True, host="0.0.0.0", port=8887)
