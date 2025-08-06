#!/usr/bin/env python3
"""
K8sClient 高级查询功能示例
包括分页、排序、筛选等功能的使用方法
"""

import sys
import os
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dingo_command.common.k8s_client import K8sClient

def demo_basic_query():
    """演示基本查询功能"""
    print("=== 基本查询功能演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 基本查询 - 获取所有 pods
        print("1. 获取所有 pods:")
        result = client.get_resource("pods")
        print(f"   找到 {result['total_count']} 个 pods")
        
        # 查询特定命名空间的资源
        print("\n2. 获取 kube-system 命名空间的 pods:")
        result = client.get_resource("pods", namespace="kube-system")
        print(f"   找到 {result['total_count']} 个 pods")
        
        # 使用标签选择器
        print("\n3. 使用标签选择器查询:")
        result = client.get_resource("pods", label_selector="app=nginx")
        print(f"   找到 {result['total_count']} 个带有 app=nginx 标签的 pods")
        
    except Exception as e:
        print(f"基本查询演示失败: {e}")

def demo_pagination():
    """演示分页功能"""
    print("\n=== 分页功能演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 分页查询
        print("1. 分页查询 pods (每页 5 个):")
        result = client.get_resource_list_with_pagination(
            resource_type="pods",
            page_size=5,
            page_number=1
        )
        
        pagination = result['pagination']
        print(f"   第 {pagination['page_number']} 页 / 共 {pagination['total_pages']} 页")
        print(f"   总共 {pagination['total_count']} 个资源")
        print(f"   本页 {len(result['items'])} 个资源")
        print(f"   有下一页: {pagination['has_next']}")
        
        # 获取下一页
        if pagination['has_next']:
            print("\n2. 获取下一页:")
            result = client.get_resource_list_with_pagination(
                resource_type="pods",
                page_size=5,
                page_number=2
            )
            pagination = result['pagination']
            print(f"   第 {pagination['page_number']} 页，本页 {len(result['items'])} 个资源")
        
    except Exception as e:
        print(f"分页演示失败: {e}")

def demo_sorting():
    """演示排序功能"""
    print("\n=== 排序功能演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 按名称排序
        print("1. 按名称升序排序:")
        result = client.get_resource(
            resource_type="pods",
            sort_by="metadata.name",
            sort_order="asc"
        )
        
        if result['items']:
            print("   前 3 个 pods:")
            for i, pod in enumerate(result['items'][:3]):
                name = pod.get('metadata', {}).get('name', 'Unknown')
                print(f"   {i+1}. {name}")
        
        # 按创建时间排序
        print("\n2. 按创建时间降序排序:")
        result = client.get_resource(
            resource_type="pods",
            sort_by="metadata.creationTimestamp",
            sort_order="desc"
        )
        
        if result['items']:
            print("   最新的 3 个 pods:")
            for i, pod in enumerate(result['items'][:3]):
                name = pod.get('metadata', {}).get('name', 'Unknown')
                created = pod.get('metadata', {}).get('creationTimestamp', 'Unknown')
                print(f"   {i+1}. {name} (创建于: {created})")
        
    except Exception as e:
        print(f"排序演示失败: {e}")

def demo_filtering():
    """演示筛选功能"""
    print("\n=== 筛选功能演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 按状态筛选
        print("1. 筛选运行中的 pods:")
        result = client.get_resources_by_status(
            resource_type="pods",
            status_conditions={"phase": "Running"}
        )
        print(f"   找到 {result['total_count']} 个运行中的 pods")
        
        # 按年龄筛选
        print("\n2. 筛选创建时间超过 1 小时的 pods:")
        one_hour_ago = 3600  # 1 小时 = 3600 秒
        result = client.get_resources_by_age(
            resource_type="pods",
            min_age_seconds=one_hour_ago
        )
        print(f"   找到 {result['total_count']} 个超过 1 小时的 pods")
        
        # 按年龄筛选 - 最近 10 分钟创建的
        print("\n3. 筛选最近 10 分钟创建的 pods:")
        ten_minutes = 600  # 10 分钟 = 600 秒
        result = client.get_resources_by_age(
            resource_type="pods",
            max_age_seconds=ten_minutes
        )
        print(f"   找到 {result['total_count']} 个最近 10 分钟创建的 pods")
        
    except Exception as e:
        print(f"筛选演示失败: {e}")

def demo_search():
    """演示搜索功能"""
    print("\n=== 搜索功能演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 搜索包含特定关键词的资源
        print("1. 搜索名称包含 'kube' 的 pods:")
        result = client.search_resources(
            resource_type="pods",
            search_terms=["kube"],
            search_fields=["metadata.name"]
        )
        print(f"   找到 {result['total_count']} 个匹配的 pods")
        
        # 多关键词搜索
        print("\n2. 搜索包含 'system' 的资源:")
        result = client.search_resources(
            resource_type="pods",
            search_terms=["system"],
            search_fields=["metadata.name", "metadata.namespace"]
        )
        print(f"   找到 {result['total_count']} 个匹配的 pods")
        
    except Exception as e:
        print(f"搜索演示失败: {e}")

def demo_advanced_filtering():
    """演示高级筛选功能"""
    print("\n=== 高级筛选功能演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 自定义过滤函数
        def custom_filter(pod):
            """自定义过滤器：筛选具有特定容器镜像的 pods"""
            containers = pod.get('spec', {}).get('containers', [])
            for container in containers:
                image = container.get('image', '')
                if 'nginx' in image.lower():
                    return True
            return False
        
        print("1. 使用自定义过滤器筛选使用 nginx 镜像的 pods:")
        result = client.get_resource(
            resource_type="pods",
            filter_func=custom_filter
        )
        print(f"   找到 {result['total_count']} 个使用 nginx 镜像的 pods")
        
        # 组合多种条件
        print("\n2. 组合查询：kube-system 命名空间中运行中的 pods，按名称排序:")
        result = client.get_resource(
            resource_type="pods",
            namespace="kube-system",
            field_selector="status.phase=Running",
            sort_by="metadata.name",
            sort_order="asc"
        )
        print(f"   找到 {result['total_count']} 个匹配的 pods")
        
    except Exception as e:
        print(f"高级筛选演示失败: {e}")

def demo_deployments_query():
    """演示 Deployment 查询"""
    print("\n=== Deployment 查询演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 查询所有 deployments
        print("1. 获取所有 deployments:")
        result = client.get_resource("deployments")
        print(f"   找到 {result['total_count']} 个 deployments")
        
        # 按副本数排序
        print("\n2. 按副本数降序排序:")
        result = client.get_resource(
            resource_type="deployments",
            sort_by="spec.replicas",
            sort_order="desc"
        )
        
        if result['items']:
            print("   副本数最多的 3 个 deployments:")
            for i, deployment in enumerate(result['items'][:3]):
                name = deployment.get('metadata', {}).get('name', 'Unknown')
                replicas = deployment.get('spec', {}).get('replicas', 0)
                print(f"   {i+1}. {name} (副本数: {replicas})")
        
    except Exception as e:
        print(f"Deployment 查询演示失败: {e}")

def main():
    """主函数"""
    print("K8sClient 高级查询功能演示")
    print("=" * 50)
    
    try:
        demo_basic_query()
        demo_pagination()
        demo_sorting()
        demo_filtering()
        demo_search()
        demo_advanced_filtering()
        demo_deployments_query()
        
        print("\n" + "=" * 50)
        print("演示完成！")
        
    except Exception as e:
        print(f"\n演示过程中发生错误: {e}")
        print("请确保有可用的 Kubernetes 集群连接")

if __name__ == "__main__":
    main()
