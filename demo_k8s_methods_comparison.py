#!/usr/bin/env python3
"""
K8sClient 使用示例：展示 get_resource 和 list_resource 的区别
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dingo_command.common.k8s_client import K8sClient

def demo_get_resource():
    """演示原有的 get_resource 方法（简单查询）"""
    print("=== 原有的 get_resource 方法（简单查询）===\n")
    
    try:
        client = K8sClient()
        
        # 基本查询 - 获取所有 pods
        print("1. 获取所有 pods:")
        pods = client.get_resource("pods")
        if pods:
            print(f"   找到 {len(pods)} 个 pods")
            # 显示前 3 个 pod 的名称
            for i, pod in enumerate(pods[:3]):
                name = pod.get('metadata', {}).get('name', 'Unknown')
                namespace = pod.get('metadata', {}).get('namespace', 'Unknown')
                print(f"   {i+1}. {name} (namespace: {namespace})")
        else:
            print("   查询失败或没有找到 pods")
        
        # 查询特定命名空间的资源
        print("\n2. 获取 kube-system 命名空间的 pods:")
        kube_pods = client.get_resource("pods", namespace="kube-system")
        if kube_pods:
            print(f"   找到 {len(kube_pods)} 个 pods")
        else:
            print("   查询失败或没有找到 pods")
        
        # 使用标签选择器
        print("\n3. 使用标签选择器查询:")
        labeled_pods = client.get_resource("pods", label_selector="app=nginx")
        if labeled_pods:
            print(f"   找到 {len(labeled_pods)} 个带有 app=nginx 标签的 pods")
        else:
            print("   没有找到带有 app=nginx 标签的 pods")
        
    except Exception as e:
        print(f"get_resource 演示失败: {e}")

def demo_list_resource():
    """演示新的 list_resource 方法（高级查询）"""
    print("\n=== 新的 list_resource 方法（高级查询）===\n")
    
    try:
        client = K8sClient()
        
        # 基本查询
        print("1. 基本查询（返回详细信息）:")
        result = client.list_resource("pods")
        print(f"   找到 {result['total_count']} 个 pods")
        print(f"   元数据: {result['metadata']}")
        
        # 分页查询
        print("\n2. 分页查询（限制 5 个）:")
        result = client.list_resource("pods", limit=5)
        print(f"   返回 {len(result['items'])} 个 pods")
        continue_token = result['metadata'].get('continue')
        if continue_token:
            print(f"   有下一页，继续令牌: {continue_token[:20]}...")
        
        # 排序查询
        print("\n3. 按名称排序:")
        result = client.list_resource(
            resource_type="pods",
            sort_by="metadata.name",
            sort_order="asc"
        )
        
        if result['items']:
            print("   前 3 个 pods（按名称排序）:")
            for i, pod in enumerate(result['items'][:3]):
                name = pod.get('metadata', {}).get('name', 'Unknown')
                print(f"   {i+1}. {name}")
        
        # 自定义过滤
        print("\n4. 自定义过滤（筛选运行中的 pods）:")
        def running_filter(pod):
            return pod.get('status', {}).get('phase') == 'Running'
        
        result = client.list_resource(
            resource_type="pods",
            filter_func=running_filter
        )
        print(f"   找到 {result['total_count']} 个运行中的 pods")
        
    except Exception as e:
        print(f"list_resource 演示失败: {e}")

def demo_pagination():
    """演示分页功能"""
    print("\n=== 分页功能演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 使用分页方法
        print("1. 使用 get_resource_list_with_pagination:")
        result = client.get_resource_list_with_pagination(
            resource_type="pods",
            page_size=3,
            page_number=1
        )
        
        pagination = result['pagination']
        print(f"   第 {pagination['page_number']} 页 / 共 {pagination['total_pages']} 页")
        print(f"   总共 {pagination['total_count']} 个资源")
        print(f"   本页 {len(result['items'])} 个资源")
        
    except Exception as e:
        print(f"分页演示失败: {e}")

def demo_search_and_filter():
    """演示搜索和筛选功能"""
    print("\n=== 搜索和筛选功能演示 ===\n")
    
    try:
        client = K8sClient()
        
        # 搜索功能
        print("1. 搜索包含 'kube' 的 pods:")
        result = client.search_resources(
            resource_type="pods",
            search_terms=["kube"],
            search_fields=["metadata.name"]
        )
        print(f"   找到 {result['total_count']} 个匹配的 pods")
        
        # 按状态筛选
        print("\n2. 筛选运行中的 pods:")
        result = client.get_resources_by_status(
            resource_type="pods",
            status_conditions={"phase": "Running"}
        )
        print(f"   找到 {result['total_count']} 个运行中的 pods")
        
        # 按年龄筛选
        print("\n3. 筛选最近 1 小时创建的 pods:")
        result = client.get_resources_by_age(
            resource_type="pods",
            max_age_seconds=3600  # 1 小时
        )
        print(f"   找到 {result['total_count']} 个最近 1 小时创建的 pods")
        
    except Exception as e:
        print(f"搜索和筛选演示失败: {e}")

def demo_comparison():
    """演示两种方法的对比"""
    print("\n=== get_resource vs list_resource 对比 ===\n")
    
    try:
        client = K8sClient()
        
        print("使用 get_resource (简单方法):")
        pods_simple = client.get_resource("pods", namespace="default")
        if pods_simple is not None:
            print(f"  返回类型: {type(pods_simple)}")
            print(f"  结果数量: {len(pods_simple)}")
            print("  返回格式: 直接的资源列表")
        
        print("\n使用 list_resource (高级方法):")
        pods_advanced = client.list_resource("pods", namespace="default")
        print(f"  返回类型: {type(pods_advanced)}")
        print(f"  结果数量: {pods_advanced['total_count']}")
        print("  返回格式: 包含 items, metadata, total_count 的字典")
        print(f"  元数据键: {list(pods_advanced['metadata'].keys())}")
        
        print("\n总结:")
        print("- get_resource: 简单易用，向后兼容，适合基本查询")
        print("- list_resource: 功能强大，支持分页/排序/筛选，适合复杂查询")
        
    except Exception as e:
        print(f"对比演示失败: {e}")

def main():
    """主函数"""
    print("K8sClient 方法使用演示")
    print("=" * 60)
    
    try:
        demo_get_resource()
        demo_list_resource()
        demo_pagination()
        demo_search_and_filter()
        demo_comparison()
        
        print("\n" + "=" * 60)
        print("演示完成！")
        
        print("\n使用建议:")
        print("- 简单查询: 使用 get_resource()")
        print("- 复杂查询: 使用 list_resource()")
        print("- 分页查询: 使用 get_resource_list_with_pagination()")
        print("- 搜索功能: 使用 search_resources()")
        print("- 状态筛选: 使用 get_resources_by_status()")
        print("- 年龄筛选: 使用 get_resources_by_age()")
        
    except Exception as e:
        print(f"\n演示过程中发生错误: {e}")
        print("请确保有可用的 Kubernetes 集群连接")

if __name__ == "__main__":
    main()
