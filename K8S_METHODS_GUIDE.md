# K8sClient 方法使用指南

## 概述

`K8sClient` 现在提供两套查询方法：

1. **`get_resource`** - 简单查询方法，保持向后兼容性
2. **`list_resource`** - 高级查询方法，支持分页、排序和筛选

## 方法对比

### get_resource (简单方法)

**特点:**
- 保持向后兼容性
- 简单易用
- 直接返回资源列表
- 适合基本查询需求

**语法:**
```python
client.get_resource(
    resource_type: str,
    api_version: Optional[str] = None,
    namespace: Optional[str] = None,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]
```

**示例:**
```python
client = K8sClient()

# 获取所有 pods
pods = client.get_resource("pods")

# 获取特定命名空间的 pods
pods = client.get_resource("pods", namespace="default")

# 使用标签选择器
pods = client.get_resource("pods", label_selector="app=nginx")

# 使用字段选择器
running_pods = client.get_resource("pods", field_selector="status.phase=Running")
```

### list_resource (高级方法)

**特点:**
- 支持分页、排序、筛选
- 返回详细的元数据信息
- 支持自定义过滤函数
- 适合复杂查询需求

**语法:**
```python
client.list_resource(
    resource_type: str,
    api_version: Optional[str] = None,
    namespace: Optional[str] = None,
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
    limit: Optional[int] = None,
    continue_token: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    filter_func: Optional[callable] = None
) -> Dict[str, Any]
```

**返回格式:**
```python
{
    'items': [...],  # 资源对象列表
    'metadata': {
        'continue': '...',  # 分页继续令牌
        'remainingItemCount': 100,  # 剩余项数
        'resourceVersion': '12345'  # 资源版本
    },
    'total_count': 25  # 当前返回的项数
}
```

**示例:**
```python
client = K8sClient()

# 基本查询
result = client.list_resource("pods")
pods = result['items']

# 分页查询
result = client.list_resource("pods", limit=10)

# 排序查询
result = client.list_resource(
    resource_type="pods",
    sort_by="metadata.creationTimestamp",
    sort_order="desc"
)

# 自定义过滤
def running_filter(pod):
    return pod.get('status', {}).get('phase') == 'Running'

result = client.list_resource("pods", filter_func=running_filter)
```

## 高级查询方法

### 1. 分页查询

```python
# 第一种方式：使用 list_resource 的原生分页
result = client.list_resource("pods", limit=20)
continue_token = result['metadata']['continue']

# 获取下一页
next_result = client.list_resource("pods", limit=20, continue_token=continue_token)

# 第二种方式：使用便利的分页方法
result = client.get_resource_list_with_pagination(
    resource_type="pods",
    page_size=20,
    page_number=1
)

print(f"第 {result['pagination']['page_number']} 页")
print(f"总页数: {result['pagination']['total_pages']}")
print(f"是否有下一页: {result['pagination']['has_next']}")
```

### 2. 搜索功能

```python
# 在资源名称中搜索
result = client.search_resources(
    resource_type="pods",
    search_terms=["nginx"],
    search_fields=["metadata.name"]
)

# 在多个字段中搜索
result = client.search_resources(
    resource_type="pods",
    search_terms=["kube", "system"],
    search_fields=["metadata.name", "metadata.namespace"],
    case_sensitive=False
)
```

### 3. 状态筛选

```python
# 筛选运行中的 pods
result = client.get_resources_by_status(
    resource_type="pods",
    status_conditions={"phase": "Running"}
)

# 筛选就绪的 deployments
result = client.get_resources_by_status(
    resource_type="deployments",
    status_conditions={
        "readyReplicas": 3,
        "replicas": 3
    }
)
```

### 4. 年龄筛选

```python
# 筛选超过 1 小时的资源
result = client.get_resources_by_age(
    resource_type="pods",
    min_age_seconds=3600
)

# 筛选最近 10 分钟创建的资源
result = client.get_resources_by_age(
    resource_type="pods",
    max_age_seconds=600
)

# 筛选特定时间范围的资源
result = client.get_resources_by_age(
    resource_type="pods",
    min_age_seconds=1800,  # 30 分钟前
    max_age_seconds=3600   # 1 小时前
)
```

### 5. 排序功能

```python
# 按名称排序
result = client.list_resource(
    resource_type="pods",
    sort_by="metadata.name",
    sort_order="asc"
)

# 按创建时间排序
result = client.list_resource(
    resource_type="pods",
    sort_by="metadata.creationTimestamp",
    sort_order="desc"
)

# 按副本数排序（针对 deployments）
result = client.list_resource(
    resource_type="deployments",
    sort_by="spec.replicas",
    sort_order="desc"
)

# 按容器镜像排序
result = client.list_resource(
    resource_type="pods",
    sort_by="spec.containers[0].image",
    sort_order="asc"
)
```

### 6. 自定义过滤

```python
# 筛选使用特定镜像的 pods
def nginx_filter(pod):
    containers = pod.get('spec', {}).get('containers', [])
    return any('nginx' in container.get('image', '') for container in containers)

result = client.list_resource("pods", filter_func=nginx_filter)

# 筛选高 CPU 请求的 pods
def high_cpu_filter(pod):
    containers = pod.get('spec', {}).get('containers', [])
    for container in containers:
        requests = container.get('resources', {}).get('requests', {})
        cpu = requests.get('cpu', '0')
        if cpu.endswith('m') and int(cpu[:-1]) > 500:
            return True
        elif cpu and float(cpu) > 0.5:
            return True
    return False

result = client.list_resource("pods", filter_func=high_cpu_filter)
```

## 使用建议

### 什么时候使用 get_resource

1. **简单查询**: 只需要获取资源列表，不需要复杂功能
2. **向后兼容**: 升级现有代码时保持兼容性
3. **快速原型**: 快速编写测试或演示代码
4. **基础脚本**: 简单的自动化脚本

```python
# 适合使用 get_resource 的场景
pods = client.get_resource("pods", namespace="default")
if pods:
    for pod in pods:
        print(pod['metadata']['name'])
```

### 什么时候使用 list_resource

1. **复杂查询**: 需要排序、筛选或分页功能
2. **生产环境**: 需要处理大量数据或性能优化
3. **用户界面**: 为 Web 或桌面应用提供数据
4. **监控工具**: 需要详细的元数据信息

```python
# 适合使用 list_resource 的场景
result = client.list_resource(
    resource_type="pods",
    namespace="production",
    sort_by="metadata.creationTimestamp",
    sort_order="desc",
    limit=50
)

for pod in result['items']:
    print(f"{pod['metadata']['name']} - {pod['status']['phase']}")
    
# 检查是否还有更多数据
if result['metadata']['continue']:
    print("还有更多数据可以获取")
```

## 迁移指南

### 从旧代码迁移

如果您现有的代码使用了增强版的 `get_resource`（带有分页、排序等参数），需要迁移到 `list_resource`：

**旧代码:**
```python
# 这种用法已不再支持
result = client.get_resource(
    resource_type="pods",
    sort_by="metadata.name",
    limit=10
)
items = result['items']
```

**新代码:**
```python
# 使用 list_resource 替代
result = client.list_resource(
    resource_type="pods",
    sort_by="metadata.name",
    limit=10
)
items = result['items']
```

### 简化现有代码

如果您的代码只需要简单查询，可以简化为使用 `get_resource`：

**复杂代码:**
```python
result = client.list_resource("pods", namespace="default")
pods = result['items']
```

**简化代码:**
```python
pods = client.get_resource("pods", namespace="default")
```

## 性能考虑

1. **`get_resource`**: 适合小规模查询，内存使用较少
2. **`list_resource`**: 适合大规模查询，支持服务器端分页
3. **分页查询**: 对于大集群，始终使用分页避免内存问题
4. **筛选优化**: 优先使用服务器端筛选（label_selector, field_selector）而不是客户端筛选

## 错误处理

```python
# get_resource 错误处理
pods = client.get_resource("pods")
if pods is None:
    print("查询失败")
else:
    print(f"找到 {len(pods)} 个 pods")

# list_resource 错误处理
result = client.list_resource("pods")
if 'error' in result['metadata']:
    print(f"查询失败: {result['metadata']['error']}")
else:
    print(f"找到 {result['total_count']} 个 pods")
```

这种设计既保持了向后兼容性，又提供了强大的高级功能，满足不同场景的使用需求。
