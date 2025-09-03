import base64
import os
import sys
import time
from contextlib import contextmanager

import grpc
from grpc import ssl_channel_credentials

# 通过protoc生成了对应的Python gRPC代码
from dingo_command.common.grpc_nerdctl import nerdctl_pb2 as pb
from dingo_command.common.grpc_nerdctl import nerdctl_pb2_grpc as pb_grpc

from dingo_command.utils.constant import GRPC_SECRET, GRPC_KEY, GRPC_CA

API_KEY = "d15768d3-2088-44b5-9fba-0a1dd82393e8"
SERVER_HOST = "nerdctl-api.internal.alayanew.com:6060"
SERVER_PORT = "6060"
MAX_RETRIES = 3

@contextmanager
def grpc_client(secret_path, key_path, ca_path, host_ip):
    """创建并管理gRPC客户端连接的上下文管理器"""
    # 读取TLS证书文件
    with open(secret_path, 'rb') as f:
        client_cert = f.read()
    with open(key_path, 'rb') as f:
        client_key = f.read()
    with open(ca_path, 'rb') as f:
        ca_cert = f.read()

    # 创建TLS凭证
    credentials = ssl_channel_credentials(
        root_certificates=ca_cert,
        private_key=client_key,
        certificate_chain=client_cert
    )

    # 创建gRPC通道
    # channel = grpc.secure_channel(host_ip + ":" + SERVER_PORT, credentials)
    channel = grpc.secure_channel(SERVER_HOST, credentials)
    try:
        yield channel
    finally:
        channel.close()

def run_commit(host_ip, req_param):
    """执行commit命令"""
    with grpc_client(os.getcwd() + GRPC_SECRET, os.getcwd() + GRPC_KEY, os.getcwd() + GRPC_CA, host_ip) as channel:
        client = pb_grpc.NerdctlServiceStub(channel)

        # 处理containerId前缀
        container_id = req_param['container_id']
        if container_id and container_id.startswith("containerd://"):
            container_id = container_id[len("containerd://"):]

        print(f"Committing container: {container_id} -> {req_param['image']}")

        # 创建metadata
        md = [('api-key', API_KEY)]

        # 创建请求对象
        request = pb.CommitRequest(
            containerId=container_id,
            image=req_param['image']
        )

        try:
            # 调用gRPC流式方法
            stream = client.CommitStream(request, metadata=md)

            # 处理流响应
            for response in stream:
                print(f"run_commit commmit:{response}")
                if response.code in (0, 100):
                    sys.stdout.write(response.msg)
                elif response.code == 1:
                    sys.stderr.write(f"Error: {response.msg}\n")
                else:
                    sys.stdout.write(f"[code {response.code}] {response.msg}\n")

        except grpc.RpcError as e:
            print(f"Commit failed: {e}")
            # sys.exit(1)
            raise e


def run_push(host_ip, req_param):
    """执行push命令"""
    # 准备基本认证信息
    auth = base64.b64encode(f"{req_param.username}:{req_param.password}".encode()).decode()
    md = [
        ('api-key', API_KEY),
        ('authorization', f'Basic {auth}')
    ]

    with grpc_client(GRPC_SECRET, GRPC_KEY, GRPC_CA, host_ip) as channel:
        client = pb_grpc.NerdctlServiceStub(channel)

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"Push attempt {attempt}/{MAX_RETRIES}...")

            try:
                # 创建请求对象
                request = pb.PushRequest(
                    image=req_param['image'],
                    username=req_param['username'],
                    password=req_param['password']
                )

                # 调用gRPC流式方法
                stream = client.PushStream(request, metadata=md)

                # 处理流响应
                try:
                    for response in stream:
                        sys.stdout.write(response.msg)

                    print("Push complete.")
                    return

                except grpc.RpcError as e:
                    print(f"Stream receive error: {e}")
                    if attempt == MAX_RETRIES:
                        print("Push failed after retries.")
                        # sys.exit(1)
                        raise e

            except grpc.RpcError as e:
                print(f"Push error: {e}")
                if attempt == MAX_RETRIES:
                    print("Push failed after retries.")
                    # sys.exit(1)
                    raise e

            time.sleep(2 if attempt < MAX_RETRIES else 0)
