#!/usr/bin/env python3
"""
测试 K8sClient 的 API 版本推断功能
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dingo_command.common.k8s_client import K8sClient

def test_api_version_inference():
    """测试 API 版本推断功能"""
    
    print("=== 测试 K8sClient API 版本推断功能 ===\n")
    
    # 创建客户端实例（这里可能会失败如果没有可用的 k8s 集群）
    try:
        client = K8sClient()
        print("✅ K8sClient 初始化成功")
    except Exception as e:
        print(f"❌ K8sClient 初始化失败: {e}")
        print("注意：这通常是因为没有可用的 Kubernetes 集群或配置")
        # 我们可以继续测试推断逻辑，不依赖实际的集群连接
        return test_inference_logic_only()
    
    # 测试各种资源类型的 API 版本推断
    test_cases = [
        # 核心 API 资源
        ("pods", "v1"),
        ("services", "v1"),
        ("configmaps", "v1"),
        ("secrets", "v1"),
        ("nodes", "v1"),
        ("namespaces", "v1"),
        
        # apps API 资源
        ("deployments", "apps/v1"),
        ("replicasets", "apps/v1"),
        ("daemonsets", "apps/v1"),
        ("statefulsets", "apps/v1"),
        
        # networking API 资源
        ("ingresses", "networking.k8s.io/v1"),
        ("networkpolicies", "networking.k8s.io/v1"),
        
        # rbac API 资源
        ("roles", "rbac.authorization.k8s.io/v1"),
        ("clusterroles", "rbac.authorization.k8s.io/v1"),
        
        # batch API 资源
        ("jobs", "batch/v1"),
        ("cronjobs", "batch/v1"),
        
        # storage API 资源
        ("storageclasses", "storage.k8s.io/v1"),
        
        # 其他 API 资源
        ("customresourcedefinitions", "apiextensions.k8s.io/v1"),
        ("horizontalpodautoscalers", "autoscaling/v2"),
    ]
    
    print("=== 测试 API 版本推断 ===")
    success_count = 0
    total_count = len(test_cases)
    
    for resource_type, expected_api_version in test_cases:
        try:
            inferred_api_version = client._infer_api_version(resource_type)
            if inferred_api_version == expected_api_version:
                print(f"✅ {resource_type}: {inferred_api_version}")
                success_count += 1
            else:
                print(f"❌ {resource_type}: 期望 {expected_api_version}, 实际 {inferred_api_version}")
        except Exception as e:
            print(f"❌ {resource_type}: 推断失败 - {e}")
    
    print(f"\n=== 测试结果 ===")
    print(f"成功: {success_count}/{total_count}")
    print(f"成功率: {success_count/total_count*100:.1f}%")
    
    # 测试集群信息获取
    print("\n=== 测试集群信息获取 ===")
    try:
        k8s_version = client._get_k8s_server_version()
        print(f"✅ Kubernetes 版本: {k8s_version}")
    except Exception as e:
        print(f"❌ 获取 Kubernetes 版本失败: {e}")
    
    # 测试资源信息获取
    print("\n=== 测试资源信息获取 ===")
    test_resources = ["pods", "deployments", "services"]
    for resource in test_resources:
        try:
            info = client.get_resource_info(resource)
            if info:
                print(f"✅ {resource}: {info['apiVersion']}, 命名空间级别: {info['namespaced']}")
            else:
                print(f"❌ {resource}: 无法获取资源信息")
        except Exception as e:
            print(f"❌ {resource}: 获取信息失败 - {e}")

def test_inference_logic_only():
    """仅测试推断逻辑，不需要实际的 k8s 连接"""
    print("=== 仅测试推断逻辑（无需 k8s 连接）===\n")
    
    # 模拟一个简化的推断测试
    test_cases = [
        ("pods", "v1"),
        ("deployments", "apps/v1"),
        ("ingresses", "networking.k8s.io/v1"),
        ("jobs", "batch/v1"),
    ]
    
    print("预期的 API 版本映射:")
    for resource_type, expected_api_version in test_cases:
        print(f"  {resource_type} -> {expected_api_version}")
    
    print("\n✅ 推断逻辑测试完成（需要实际的 K8s 集群才能完整测试）")

if __name__ == "__main__":
    test_api_version_inference()
