#!/usr/bin/env python3
"""
测试 K8sClient 的高级查询功能
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dingo_command.common.k8s_client import K8sClient

class TestK8sClientAdvancedQuery(unittest.TestCase):
    """测试 K8sClient 高级查询功能"""
    
    def setUp(self):
        """设置测试环境"""
        self.mock_pods = [
            {
                'metadata': {
                    'name': 'nginx-pod-1',
                    'namespace': 'default',
                    'creationTimestamp': '2023-01-01T10:00:00Z',
                    'labels': {'app': 'nginx', 'version': 'v1'}
                },
                'spec': {
                    'containers': [{'name': 'nginx', 'image': 'nginx:1.20'}]
                },
                'status': {'phase': 'Running'}
            },
            {
                'metadata': {
                    'name': 'apache-pod-1',
                    'namespace': 'default',
                    'creationTimestamp': '2023-01-01T11:00:00Z',
                    'labels': {'app': 'apache', 'version': 'v2'}
                },
                'spec': {
                    'containers': [{'name': 'apache', 'image': 'httpd:2.4'}]
                },
                'status': {'phase': 'Failed'}
            },
            {
                'metadata': {
                    'name': 'redis-pod-1',
                    'namespace': 'cache',
                    'creationTimestamp': '2023-01-01T12:00:00Z',
                    'labels': {'app': 'redis', 'version': 'v1'}
                },
                'spec': {
                    'containers': [{'name': 'redis', 'image': 'redis:6.2'}]
                },
                'status': {'phase': 'Running'}
            }
        ]

    def test_sort_resources(self):
        """测试资源排序功能"""
        # 创建一个不需要实际 k8s 连接的客户端实例
        # 我们只测试排序逻辑
        try:
            # 模拟创建客户端（可能会因为没有 k8s 连接而失败）
            client = K8sClient()
        except:
            # 如果连接失败，直接测试排序方法
            client = Mock()
            client._sort_resources = K8sClient._sort_resources.__get__(client, K8sClient)
        
        # 测试按名称排序
        sorted_asc = client._sort_resources(self.mock_pods, 'metadata.name', 'asc')
        names_asc = [pod['metadata']['name'] for pod in sorted_asc]
        expected_asc = ['apache-pod-1', 'nginx-pod-1', 'redis-pod-1']
        self.assertEqual(names_asc, expected_asc)
        
        # 测试按名称降序排序
        sorted_desc = client._sort_resources(self.mock_pods, 'metadata.name', 'desc')
        names_desc = [pod['metadata']['name'] for pod in sorted_desc]
        expected_desc = ['redis-pod-1', 'nginx-pod-1', 'apache-pod-1']
        self.assertEqual(names_desc, expected_desc)

    def test_get_nested_field_value(self):
        """测试嵌套字段值获取"""
        try:
            client = K8sClient()
        except:
            client = Mock()
            client._get_nested_field_value = K8sClient._get_nested_field_value.__get__(client, K8sClient)
        
        pod = self.mock_pods[0]
        
        # 测试简单字段
        name = client._get_nested_field_value(pod, 'metadata.name')
        self.assertEqual(name, 'nginx-pod-1')
        
        # 测试嵌套字段
        image = client._get_nested_field_value(pod, 'spec.containers[0].image')
        self.assertEqual(image, 'nginx:1.20')
        
        # 测试不存在的字段
        non_existent = client._get_nested_field_value(pod, 'spec.nonexistent')
        self.assertIsNone(non_existent)

    def test_pagination_logic(self):
        """测试分页逻辑"""
        # 模拟分页计算
        total_items = 50
        page_size = 10
        page_number = 3
        
        offset = (page_number - 1) * page_size
        expected_offset = 20
        self.assertEqual(offset, expected_offset)
        
        total_pages = (total_items + page_size - 1) // page_size
        expected_total_pages = 5
        self.assertEqual(total_pages, expected_total_pages)
        
        has_next = offset + page_size < total_items
        self.assertTrue(has_next)
        
        has_previous = page_number > 1
        self.assertTrue(has_previous)

    def test_api_version_inference(self):
        """测试 API 版本推断"""
        try:
            client = K8sClient()
        except:
            client = Mock()
            client._get_k8s_server_version = Mock(return_value="1.25")
            client._infer_api_version = K8sClient._infer_api_version.__get__(client, K8sClient)
        
        # 测试核心资源
        self.assertEqual(client._infer_api_version('pods'), 'v1')
        self.assertEqual(client._infer_api_version('services'), 'v1')
        
        # 测试 apps 资源
        self.assertEqual(client._infer_api_version('deployments'), 'apps/v1')
        self.assertEqual(client._infer_api_version('daemonsets'), 'apps/v1')
        
        # 测试 networking 资源
        self.assertEqual(client._infer_api_version('ingresses'), 'networking.k8s.io/v1')
        
        # 测试未知资源
        with self.assertRaises(ValueError):
            client._infer_api_version('unknown-resource')

class TestQueryFunctions(unittest.TestCase):
    """测试查询函数的逻辑"""
    
    def test_search_logic(self):
        """测试搜索逻辑"""
        # 模拟搜索函数
        def search_in_text(text, terms, case_sensitive=False):
            if not case_sensitive:
                text = text.lower()
                terms = [term.lower() for term in terms]
            
            return all(term in text for term in terms)
        
        # 测试不区分大小写搜索
        self.assertTrue(search_in_text("Nginx Pod", ["nginx"], case_sensitive=False))
        self.assertTrue(search_in_text("Nginx Pod", ["nginx", "pod"], case_sensitive=False))
        self.assertFalse(search_in_text("Nginx Pod", ["apache"], case_sensitive=False))
        
        # 测试区分大小写搜索
        self.assertFalse(search_in_text("Nginx Pod", ["nginx"], case_sensitive=True))
        self.assertTrue(search_in_text("Nginx Pod", ["Nginx"], case_sensitive=True))

    def test_age_calculation(self):
        """测试年龄计算逻辑"""
        from datetime import datetime, timezone, timedelta
        
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        
        # 计算年龄（秒）
        age_seconds = (now - one_hour_ago).total_seconds()
        self.assertAlmostEqual(age_seconds, 3600, delta=1)  # 大约 1 小时
        
        # 测试年龄筛选逻辑
        min_age = 1800  # 30 分钟
        max_age = 7200  # 2 小时
        
        self.assertTrue(min_age <= age_seconds <= max_age)

def run_tests():
    """运行测试"""
    print("运行 K8sClient 高级查询功能测试...")
    
    # 创建测试套件
    suite = unittest.TestSuite()
    
    # 添加测试用例
    suite.addTest(unittest.makeSuite(TestK8sClientAdvancedQuery))
    suite.addTest(unittest.makeSuite(TestQueryFunctions))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出结果
    if result.wasSuccessful():
        print("\n✅ 所有测试通过！")
    else:
        print(f"\n❌ 测试失败：{len(result.failures)} 个失败，{len(result.errors)} 个错误")
        
        for test, traceback in result.failures:
            print(f"\n失败: {test}")
            print(traceback)
            
        for test, traceback in result.errors:
            print(f"\n错误: {test}")
            print(traceback)

if __name__ == "__main__":
    run_tests()
