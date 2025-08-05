# K8sClient API 版本自动推断功能

## 概述

`K8sClient` 类现在支持根据资源类型和 Kubernetes 集群版本自动推断正确的 API 版本。这大大简化了 Kubernetes 资源操作的使用方式。

## 主要功能

### 1. 自动 API 版本推断

现在可以在不指定 `api_version` 的情况下查询和创建资源：

```python
from dingo_command.common.k8s_client import K8sClient

client = K8sClient()

# 查询资源时自动推断 API 版本
pods = client.get_resource("pods", namespace="default")
deployments = client.get_resource("deployments", namespace="kube-system")
ingresses = client.get_resource("ingresses")

# 创建资源时也可以自动推断 API 版本
pod_spec = {
    "kind": "Pod",
    "metadata": {"name": "test-pod", "namespace": "default"},
    "spec": {"containers": [{"name": "test", "image": "nginx"}]}
}
created_pod = client.create_resource(pod_spec, "pods")
```

### 2. 支持的资源类型

#### 核心 API (v1)
- pods, services, configmaps, secrets, serviceaccounts
- events, nodes, persistentvolumes, persistentvolumeclaims
- namespaces, endpoints, limitranges, resourcequotas
- replicationcontrollers, bindings, componentstatuses

#### Apps API (apps/v1)
- deployments, replicasets, daemonsets, statefulsets

#### Networking API
- ingresses: `networking.k8s.io/v1` (k8s 1.19+) 或 `extensions/v1beta1` (旧版本)
- networkpolicies: `networking.k8s.io/v1`
- ingressclasses: `networking.k8s.io/v1`

#### RBAC API (rbac.authorization.k8s.io/v1)
- roles, rolebindings, clusterroles, clusterrolebindings

#### Batch API
- jobs: `batch/v1`
- cronjobs: `batch/v1` (k8s 1.21+) 或 `batch/v1beta1` (旧版本)

#### Autoscaling API
- horizontalpodautoscalers: `autoscaling/v2` (k8s 1.23+) 或 `autoscaling/v1` (旧版本)

#### Policy API
- poddisruptionbudgets: `policy/v1` (k8s 1.21+) 或 `policy/v1beta1` (旧版本)
- podsecuritypolicies: `policy/v1beta1` (已在 k8s 1.25+ 中移除)

#### Storage API (storage.k8s.io/v1)
- storageclasses, volumeattachments, csinodes, csidrivers, csistoragecapacities

#### 其他 API 组
- customresourcedefinitions: `apiextensions.k8s.io/v1` (k8s 1.16+) 或 `apiextensions.k8s.io/v1beta1`
- mutatingwebhookconfigurations, validatingwebhookconfigurations: `admissionregistration.k8s.io/v1`
- certificatesigningrequests: `certificates.k8s.io/v1`
- leases: `coordination.k8s.io/v1`
- endpointslices: `discovery.k8s.io/v1`
- runtimeclasses: `node.k8s.io/v1`

### 3. 版本感知推断

系统会自动检测 Kubernetes 集群版本，并根据版本选择合适的 API 版本：

```python
# 系统会自动检测集群版本并选择合适的 API 版本
# 例如，对于 ingresses：
# - k8s 1.19+ 使用 networking.k8s.io/v1
# - k8s 1.18- 使用 extensions/v1beta1
ingresses = client.get_resource("ingresses")
```

### 4. 动态资源发现

对于未预定义的资源类型，系统会尝试通过 Kubernetes API 发现功能自动查找：

```python
# 对于自定义资源或不在预定义列表中的资源
# 系统会尝试通过 API 发现自动找到正确的 API 版本
custom_resources = client.get_resource("mycustomresources")
```

### 5. 实用工具方法

#### 获取支持的 API 版本
```python
api_versions = client.get_supported_api_versions()
print(api_versions)
# 输出: {'v1': ['pods', 'services', ...], 'apps/v1': ['deployments', ...], ...}
```

#### 查找资源的 API 版本
```python
api_version = client.find_resource_api_version("deployments")
print(api_version)  # 输出: "apps/v1"
```

#### 验证资源和 API 版本组合
```python
is_valid = client.validate_resource_and_api_version("pods", "v1")
print(is_valid)  # 输出: True
```

#### 获取资源详细信息
```python
info = client.get_resource_info("deployments")
print(info)
# 输出: {
#   "name": "deployments",
#   "kind": "Deployment",
#   "apiVersion": "apps/v1",
#   "namespaced": True,
#   ...
# }
```

## 向后兼容性

所有现有的代码都继续正常工作。如果明确指定了 `api_version`，系统会使用指定的版本而不是推断：

```python
# 明确指定 API 版本仍然有效
pods = client.get_resource("pods", api_version="v1", namespace="default")
```

## 错误处理

当无法推断 API 版本时，系统会提供清晰的错误信息：

```python
try:
    client.get_resource("unknown-resource-type")
except ValueError as e:
    print(e)  # 输出: "无法推断资源 'unknown-resource-type' 的 API 版本，请明确提供 'api_version' 参数。"
```

## 性能考虑

- API 版本推断是基于本地映射表的，性能开销很小
- Kubernetes 版本检测只在客户端初始化时执行一次
- 动态资源发现只在无法通过映射表推断时才会执行

## 最佳实践

1. **让系统自动推断**: 对于标准资源，不需要指定 `api_version`
2. **显式指定复杂情况**: 对于自定义资源或特殊情况，建议明确指定 `api_version`
3. **版本兼容性**: 在多版本环境中，系统会自动选择最合适的版本
4. **错误处理**: 总是准备处理推断失败的情况
