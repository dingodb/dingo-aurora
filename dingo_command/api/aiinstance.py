# ai相关的容器实例的创建接口
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from kubernetes.stream import stream
from kubernetes import client

from dingo_command.api.model.aiinstance import AiInstanceApiModel, AiInstanceSavaImageApiModel, AccountCreateRequest, \
    AccountUpdateRequest, AutoDeleteRequest, AutoCloseRequest, StartInstanceModel
from dingo_command.services.ai_instance import AiInstanceService
from dingo_command.services.custom_exception import Fail
from dingo_command.utils.k8s_client import get_k8s_client

router = APIRouter()
ai_instance_service = AiInstanceService()

@router.post("/ai-instance/create", summary="创建容器实例", description="创建容器实例")
async def create_ai_instance(ai_instance:AiInstanceApiModel):
    # 创建容器实例
    try:
        # 创建成功
        return ai_instance_service.create_ai_instance(ai_instance)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"创建容器实例[{ai_instance.name}]失败:{e}")


@router.post("/ai-instances/{id}/save-image", summary="容器实例保存为镜像", description="容器实例保存为镜像")
async def sava_ai_instance_to_image(id: str, request: AiInstanceSavaImageApiModel):
    # 容器实例保存为镜像
    try:
        # 容器实例保存为镜像
        return ai_instance_service.sava_ai_instance_to_image(id, request)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"容器实例[{id}]保存为镜像失败:{e}")

@router.get("/ai-instance/list", summary="查询容器实例列表", description="查询容器实例列表")
async def list_ai_instance_infos(
        uuid:str = Query(None, description="容器实例主键ID"),
        instance_name:str = Query(None, description="容器实例名称"),
        instance_status:str = Query(None, description="容器实例状态"),
        page: int = Query(1, description="页码"),
        page_size: int = Query(10, description="页数量大小"),
        sort_keys: str = Query(None, description="排序字段"),
        sort_dirs: str = Query(None, description="排序方式")):
    # 查询容器实例列表
    try:
    # 声明查询条件的dict
        query_params = {}
        # 查询条件组装
        if uuid:
            query_params['uuid'] = uuid
        if instance_name:
            query_params['instance_name'] = instance_name
        if instance_status:
            query_params['instance_status'] = instance_status
        return ai_instance_service.list_ai_instance_info(query_params, page, page_size, sort_keys, sort_dirs)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"查询容器实例列表失败:{e}")

@router.get("/ai-instance/{id}", summary="查询容器实例详情", description="查询容器实例详情")
async def get_instance_info_by_id(id:str):
    # 查询容器实例详情
    try:
        return ai_instance_service.get_ai_instance_info_by_id(id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"查询容器实例详情失败:{id}")

@router.delete("/ai-instance/{id}", summary="删除容器实例", description="根据实例id删除容器实例数据")
async def delete_instance_by_id(id:str):
    # 删除容器实例
    try:
        # 删除成功
        return ai_instance_service.delete_ai_instance_by_id(id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"删除容器实[{id}]例失败:{e}")

# 所有的websocket的连接的统一入口
@router.websocket("/ws-ai/pod/{namespace}/{pod_name}")
async def pod_console(
        websocket: WebSocket,
        namespace: str,
        pod_name: str,
        container: str = None
):
    await websocket.accept()

    try:
        k8s_client = get_k8s_client("test_wwb-2", client.CoreV1Api)
        # 创建k8s exec连接
        exec_command = [
            '/bin/sh',
            '-c',
            'TERM=xterm-256color; export TERM; [ -x /bin/bash ] && ([ -x /usr/bin/script ] && /usr/bin/script -q -c "/bin/bash" /dev/null || exec /bin/bash) || exec /bin/sh'
        ]
        print(k8s_client.list_node())
        resp = stream(
            k8s_client.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            container=container,
            command=exec_command,
            stderr=True, stdin=True,
            stdout=True, tty=True,
            _preload_content=False
        )

        # 创建异步任务处理双向数据流
        async def receive_from_ws():
            while True:
                data = await websocket.receive_text()
                resp.write_stdin(data + "\n")

        async def send_to_ws():
            while resp.is_open():
                if resp.peek_stdout():
                    output = resp.read_stdout()
                    await websocket.send_text(output)
                if resp.peek_stderr():
                    error = resp.read_stderr()
                    await websocket.send_text(f"[ERROR] {error}")
                await asyncio.sleep(0.1)

        await asyncio.gather(
            receive_from_ws(),
            send_to_ws()
        )

    except WebSocketDisconnect as e:
        resp.close()
        import traceback
        traceback.print_exc()
    except Exception as e:
        import traceback
        traceback.print_exc()
        await websocket.send_text(f"Terminal error: {str(e)}")
        await websocket.close()

@router.post("/ai-instance/{id}/start", summary="开机容器实例", description="根据实例id开机容器实例")
async def start_instance_by_id(id: str, request: Optional[StartInstanceModel] = None):
    try:
        return ai_instance_service.start_ai_instance_by_id(id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"开机容器实例失败:{id}")

@router.post("/ai-instance/{id}/stop", summary="关机容器实例", description="根据实例id关机容器实例")
async def stop_instance_by_id(id: str):
    try:
        return ai_instance_service.stop_ai_instance_by_id(id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"关机容器实例失败:{id}")

@router.post("/ai-instance/{id}/auto-close", summary="设置定时关机容器实例", description="根据实例id设置定时关机容器实例")
async def set_auto_close_instance_by_id(id: str, request: AutoCloseRequest):
    try:
        return ai_instance_service.set_auto_close_instance_by_id(id, request.auto_close_time, request.auto_close)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"设置定时关机容器实例失败:{id}")

@router.post("/ai-instance/{id}/auto-delete", summary="设置定时删除容器实例", description="根据实例id设置定时删除容器实例")
async def set_auto_delete_instance_by_id(id: str, request: AutoDeleteRequest):
    try:
        return ai_instance_service.set_auto_delete_instance_by_id(id, request.auto_delete_time, request.auto_delete)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"设置定时删除容器实例失败:{id}")

@router.post("/ai-instance/{id}/port/create", summary="容器实例端口新增端口", description="根据实例id新增端口")
async def create_port_by_id(id: str, port: int):
    try:
        return ai_instance_service.create_port_by_id(id, port)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"新增端口失败:{id}")

@router.post("/ai-instance/{id}/port/delete", summary="容器实例删除端口", description="根据实例id删除端口")
async def delete_port_by_id(id: str, port: int):
    try:
        return ai_instance_service.delete_port_by_id(id, port)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"删除端口失败:{id}")

@router.post("/ai-instance/{id}/port/list", summary="容器实例查询端口列表", description="根据实例id查询端口列表")
async def list_port_by_id(id: str):
    try:
        return ai_instance_service.list_port_by_id(id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"查询端口列表失败:{id}")

@router.get("/ai-instance/{id}/jupyter", summary="获取Jupyter访问地址", description="根据实例id返回可访问的Jupyter URL 列表与 nodePort")
async def get_jupyter_by_id(id: str):
    try:
        return ai_instance_service.get_jupyter_urls_by_id(id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"获取Jupyter访问地址失败:{id}")

# ================= 账户相关接口 =================
@router.post("/ai-account/create", summary="创建账户", description="创建账户")
async def create_ai_account(request: AccountCreateRequest):
    try:
        return ai_instance_service.create_ai_account(request.account, request.is_vip)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"创建账户失败:{e}")

@router.delete("/ai-account/{id}", summary="删除账户", description="根据ID删除账户")
async def delete_ai_account_by_id(id: str):
    try:
        return ai_instance_service.delete_ai_account_by_id(id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"删除账户失败:{e}")

@router.post("/ai-account/{id}/update", summary="更新账户", description="根据ID更新账户信息")
async def update_ai_account_by_id(id: str, request: AccountUpdateRequest):
    try:
        return ai_instance_service.update_ai_account_by_id(id, request.account, request.is_vip)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"更新账户失败:{e}")


# ========== 以下为 k8s node resoource相关接口 ==================================
@router.get("/ai/resources/{k8s_id}/statistics", summary="查询k8s资源资源统计", description="查询k8s资源资源统计")
async def get_instance_info_by_id(k8s_id:str):
    # 查询容器实例详情
    try:
        return ai_instance_service.get_k8s_node_resource_statistics(k8s_id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"查询容器实例详情失败:{id}")