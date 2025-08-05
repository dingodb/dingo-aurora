# K8sClient 高级查询功能文档

## 概述

`K8sClient` 现在支持强大的资源查询功能，包括分页、排序、筛选和搜索。这些功能可以帮助您更高效地管理和查询 Kubernetes 资源。

## 功能特性

### 1. 增强的基础查询

`get_resource` 方法现在支持更多参数：

```python
client = K8sClient()

result = client.get_resource(
    resource_type="pods",
    api_version="v1",  # 可选，会自动推断
    namespace="default",  # 可选，不指定则查询所有命名空间
    label_selector="app=nginx",  # 标签选择器
    field_selector="status.phase=Running",  # 字段选择器
    limit=50,  # 限制返回数量
    continue_token=None,  # 分页继续令牌
    sort_by="metadata.name",  # 排序字段
    sort_order="asc",  # 排序顺序：asc 或 desc
    filter_func=my_custom_filter  # 自定义过滤函数
)
```

返回格式：
```python
{
    'items': [...],  # 资源对象列表
    'metadata': {
        'continue': '...',  # 下一页的继续令牌
        'remainingItemCount': 100,  # 剩余项数
        'resourceVersion': '12345'  # 资源版本
    },
    'total_count': 25  # 当前页面的项数
}
```

### 2. 分页查询

使用 `get_resource_list_with_pagination` 方法进行分页查询：

```python
# 第一页，每页 20 个
result = client.get_resource_list_with_pagination(
    resource_type="pods",
    page_size=20,
    page_number=1,
    namespace="default",
    sort_by="metadata.creationTimestamp",
    sort_order="desc"
)

print(f"第 {result['pagination']['page_number']} 页")
print(f"总共 {result['pagination']['total_count']} 个资源")
print(f"总页数: {result['pagination']['total_pages']}")
print(f"有下一页: {result['pagination']['has_next']}")
print(f"有上一页: {result['pagination']['has_previous']}")

# 获取下一页
if result['pagination']['has_next']:
    next_page = client.get_resource_list_with_pagination(
        resource_type="pods",
        page_size=20,
        page_number=2
    )
```

### 3. 排序功能

支持按任意字段排序，包括嵌套字段：

```python
# 按名称排序
result = client.get_resource(
    resource_type="pods",
    sort_by="metadata.name",
    sort_order="asc"
)

# 按创建时间排序
result = client.get_resource(
    resource_type="pods",
    sort_by="metadata.creationTimestamp",
    sort_order="desc"
)

# 按副本数排序 (for deployments)
result = client.get_resource(
    resource_type="deployments",
    sort_by="spec.replicas",
    sort_order="desc"
)

# 按容器镜像排序
result = client.get_resource(
    resource_type="pods",
    sort_by="spec.containers[0].image",
    sort_order="asc"
)
```

### 4. 搜索功能

使用 `search_resources` 方法进行文本搜索：

```python
# 在资源名称中搜索
result = client.search_resources(
    resource_type="pods",
    search_terms=["nginx", "web"],  # 搜索包含 nginx 或 web 的资源
    search_fields=["metadata.name"],
    case_sensitive=False
)

# 在多个字段中搜索
result = client.search_resources(
    resource_type="pods",
    search_terms=["kube"],
    search_fields=["metadata.name", "metadata.namespace", "metadata.labels"],
    namespace="kube-system"
)

# 精确搜索（区分大小写）
result = client.search_resources(
    resource_type="services",
    search_terms=["ClusterIP"],
    search_fields=["spec.type"],
    case_sensitive=True
)
```

### 5. 状态筛选

使用 `get_resources_by_status` 方法按状态筛选：

```python
# 筛选运行中的 pods
result = client.get_resources_by_status(
    resource_type="pods",
    status_conditions={"phase": "Running"}
)

# 筛选就绪的 pods
result = client.get_resources_by_status(
    resource_type="pods",
    status_conditions={
        "phase": "Running",
        "conditions[0].type": "Ready",
        "conditions[0].status": "True"
    }
)

# 筛选特定状态的 deployments
result = client.get_resources_by_status(
    resource_type="deployments",
    status_conditions={
        "readyReplicas": 3,
        "replicas": 3
    }
)
```

### 6. 年龄筛选

使用 `get_resources_by_age` 方法按资源年龄筛选：

```python
# 筛选创建超过 1 小时的资源
result = client.get_resources_by_age(
    resource_type="pods",
    min_age_seconds=3600  # 1 小时
)

# 筛选最近 10 分钟创建的资源
result = client.get_resources_by_age(
    resource_type="pods",
    max_age_seconds=600  # 10 分钟
)

# 筛选特定时间范围内创建的资源
result = client.get_resources_by_age(
    resource_type="pods",
    min_age_seconds=1800,  # 30 分钟前
    max_age_seconds=3600   # 1 小时前
)
```

### 7. 自定义筛选

使用自定义过滤函数进行复杂筛选：

```python
def custom_filter(resource):
    """自定义过滤器示例"""
    # 筛选使用特定镜像的 pods
    if resource.get('kind') == 'Pod':
        containers = resource.get('spec', {}).get('containers', [])
        for container in containers:
            if 'nginx:1.20' in container.get('image', ''):
                return True
    return False

# 筛选使用特定镜像的 pods
result = client.get_resource(
    resource_type="pods",
    filter_func=custom_filter
)

def high_cpu_filter(resource):
    """筛选高 CPU 请求的资源"""
    containers = resource.get('spec', {}).get('containers', [])
    for container in containers:
        requests = container.get('resources', {}).get('requests', {})
        cpu = requests.get('cpu', '0')
        if cpu.endswith('m'):
            cpu_millicores = int(cpu[:-1])
            if cpu_millicores > 500:  # 超过 500 millicores
                return True
        elif cpu.endswith(''):
            cpu_cores = float(cpu)
            if cpu_cores > 0.5:  # 超过 0.5 核
                return True
    return False

# 筛选高 CPU 资源请求的 pods
result = client.get_resource(
    resource_type="pods",
    filter_func=high_cpu_filter
)
```

## 复杂查询示例

### 组合查询

```python
# 复杂查询：查找特定命名空间中，运行中的，使用 nginx 镜像的 pods，按创建时间排序
def nginx_filter(pod):
    containers = pod.get('spec', {}).get('containers', [])
    return any('nginx' in container.get('image', '') for container in containers)

result = client.get_resource(
    resource_type="pods",
    namespace="production",
    field_selector="status.phase=Running",
    sort_by="metadata.creationTimestamp",
    sort_order="desc",
    filter_func=nginx_filter
)
```

### 批量查询不同资源

```python
def query_multiple_resources():
    """查询多种资源类型"""
    client = K8sClient()
    results = {}
    
    resources = ["pods", "services", "deployments", "configmaps"]
    
    for resource_type in resources:
        try:
            result = client.get_resource_list_with_pagination(
                resource_type=resource_type,
                page_size=10,
                sort_by="metadata.name"
            )
            results[resource_type] = result
        except Exception as e:
            print(f"查询 {resource_type} 失败: {e}")
    
    return results
```

### 监控相关查询

```python
# 查找问题 pods
def find_problem_pods():
    """查找有问题的 pods"""
    client = K8sClient()
    
    # 查找失败的 pods
    failed_pods = client.get_resources_by_status(
        resource_type="pods",
        status_conditions={"phase": "Failed"}
    )
    
    # 查找重启次数多的 pods
    def high_restart_filter(pod):
        containers = pod.get('status', {}).get('containerStatuses', [])
        return any(container.get('restartCount', 0) > 5 for container in containers)
    
    high_restart_pods = client.get_resource(
        resource_type="pods",
        filter_func=high_restart_filter
    )
    
    # 查找长时间运行的 pods
    old_pods = client.get_resources_by_age(
        resource_type="pods",
        min_age_seconds=7 * 24 * 3600  # 7 天
    )
    
    return {
        'failed': failed_pods,
        'high_restart': high_restart_pods,
        'old': old_pods
    }
```

## 性能优化建议

### 1. 使用适当的选择器

```python
# 好的做法：使用标签选择器减少数据传输
result = client.get_resource(
    resource_type="pods",
    label_selector="app=nginx,environment=production"
)

# 而不是获取所有 pods 然后过滤
```

### 2. 分页处理大量数据

```python
# 对于大量数据，使用分页
def process_all_pods():
    client = K8sClient()
    page = 1
    page_size = 100
    
    while True:
        result = client.get_resource_list_with_pagination(
            resource_type="pods",
            page_size=page_size,
            page_number=page
        )
        
        if not result['items']:
            break
            
        # 处理当前页的数据
        for pod in result['items']:
            process_pod(pod)
        
        if not result['pagination']['has_next']:
            break
            
        page += 1
```

### 3. 缓存查询结果

```python
import time
from functools import lru_cache

class CachedK8sClient(K8sClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_ttl = 60  # 缓存 60 秒
        
    @lru_cache(maxsize=128)
    def get_cached_resource(self, resource_type, namespace=None, cache_key=None):
        """带缓存的资源查询"""
        return self.get_resource(resource_type, namespace=namespace)
```

## 错误处理

```python
def safe_query():
    """安全的查询示例"""
    client = K8sClient()
    
    try:
        result = client.get_resource("pods")
        
        if 'error' in result.get('metadata', {}):
            print(f"查询错误: {result['metadata']['error']}")
            return None
            
        return result['items']
        
    except Exception as e:
        print(f"查询失败: {e}")
        return None
```

## 最佳实践

1. **使用合适的分页大小**：通常 50-100 个资源为一页比较合适
2. **善用选择器**：优先使用 Kubernetes 原生的标签和字段选择器
3. **避免过度过滤**：在客户端进行复杂过滤会增加内存使用
4. **监控性能**：对于大集群，考虑使用缓存和异步查询
5. **错误处理**：始终检查返回结果中的错误信息

这些功能使得 `K8sClient` 成为一个强大的 Kubernetes 资源管理工具，能够满足各种复杂的查询需求。
