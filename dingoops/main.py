from contextlib import asynccontextmanager

from fastapi import FastAPI

from dingoops.api import api_router
from dingoops.jobs import bigscreen_metrics_syncer,asset_resource_relation_syncer

PROJECT_NAME = "dingoops"

app = FastAPI(
    title=PROJECT_NAME,
    openapi_url="/v1/openapi.json",
)

@app.get("/", description="根url")
async def root():
    return {"message": "Welcome to the dingoops!"}

@app.get("/v1", description="版本号url")
async def root():
    return {"message": "Welcome to the dingoops of version v1!"}

app.include_router(api_router, prefix="/v1")

# @app.on_event("startup")
# async def app_start():
#     bigscreen_metrics_syncer.start()

@asynccontextmanager
async def lifespan(app: FastAPI):
    bigscreen_metrics_syncer.start()
    #from dingoops.jobs import asset_resource_relation_syncer
    asset_resource_relation_syncer.start()
    yield
    # Add any shutdown logic here if needed

app.router.lifespan_context = lifespan

# 本地启动作测试使用
if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", reload=True, host="0.0.0.0", port=8887)
