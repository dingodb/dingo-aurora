import uuid
import sys

from db.models.bigscreen.sql import BigscreenSQL
from db.models.bigscreen.models import BigscreenMetricsConfig

bigscreen_metrics_config_data = [
    {
        "name": "gpu_average_temperature",
        "description": "GPU平均温度",
        "query": 'avg(DCGM_FI_DEV_GPU_TEMP)'
    },
    {
        "name": "gpu_total_power",
        "description": "GPU总功率",
        "query": 'sum(DCGM_FI_DEV_POWER_USAGE)',
        "extra": "机房实时功率"
    },
    {
        "name": "gpu_average_utilization",
        "description": "GPU平均使用率",
        "query": 'avg(DCGM_FI_DEV_GPU_UTIL)',
        "extra": "GPU使用率"
    },
    {
        "name": "cpu_nodes_count",
        "description": "CPU管理节点数",
        "query": 'count(node_uname_info{job="consul",hostname!~".*cpu.*"})'
    },
    {
        "name": "gpu_nodes_count",
        "description": "GPU总节点数",
        "query": 'count(node_uname_info{job="consul",hostname=~".*gpu.*"})'
    },
    {
        "name": "storage_nodes_count",
        "description": "存储节点数",
        "query": 'count(node_uname_info{job="federate_ceph_node"})'
    },
    {
        "name": "gpu_count",
        "description": "GPU卡数",
        "query": 'count(DCGM_FI_DEV_GPU_UTIL)',
        "extra": "GPU总卡数"
    },
    {
        "name": "gpu_memory_usage",
        "description": "GPU显存使用率",
        "query": 'avg(DCGM_FI_DEV_FB_USED/(DCGM_FI_DEV_FB_USED+DCGM_FI_DEV_FB_FREE))'
    },
    {
        "name": "gpu_using_nodes_count",
        "description": "GPU使用节点数",
        "query": 'count(sum(DCGM_FI_DEV_GPU_UTIL)by(Hostname) != 0)'
    },
    {
        "name": "ib_bandwidth",
        "description": "IB网络带宽",
        "query": 'sum(node_infiniband_port_data_transmitted_bytes_total + node_infiniband_port_data_received_bytes_total)',
        "extra": "IB网络总带宽",
        "unit": "byte"
    },
    {
        "name": "gpu_jobs_count",
        "description": "GPU任务数",
        "query": 'sum(node_nhc_compute_apps_count)'
    },
    {
        "name": "storage_capacity",
        "description": "存储总容量",
        "query": 'ceph_cluster_total_bytes{}',
        "unit": "byte"
    },
    {
        "name": "storage_used_capacity",
        "description": "存储使用量",
        "query": 'ceph_cluster_total_used_bytes{}',
        "unit": "byte"
    },
    {
        "name": "storage_usage",
        "description": "存储使用率",
        "query": 'ceph_cluster_total_used_bytes{}/ceph_cluster_total_bytes{}',
    },
    {
        "name": "vm_nodes_count",
        "description": "虚拟机节点数",
        "query": 'node_uname_info{job="consul",hostname!~".*k8s.*"}'
    },
    {
        "name": "memory_total",
        "description": "内存总量",
        "query": 'sum(node_memory_MemTotal_bytes{job="consul"})',
        "extra": "内存总大小",
        "unit": "byte"
    },
    {
        "name": "memory_average_utilization",
        "description": "内存平均使用率",
        "query": '(sum(node_memory_MemTotal_bytes{job="consul"} - node_memory_MemAvailable_bytes{job="consul"}) / sum(node_memory_MemTotal_bytes{job="consul"}))',
        "extra": "内存使用率",
        "unit": "percent"
    },
    {
        "name": "storage_write_throughput",
        "description": "存储实时写吞吐",
        "query": 'sum(ceph_pool_stats_wr_bytes{job="node-exporter"})',
    },
    {
        "name": "storage_read_throughput",
        "description": "存储实时读吞吐",
        "query": 'sum(ceph_pool_stats_rd_bytes{job="node-exporter"})',
    },
    {
        "name": "network_bandwidth",
        "description": "核心网络实时出口带宽",
        "query": 'librenms_ifOutOctets_rate{instance="10.222.2.11",ifName="WAN0/0/0"}',
        "unit": "bit"
    },
    {
        "name": "alert_count",
        "description": "告警数",
        "query": 'count(alerts{job="prometheus"})',
    },
    {
        "name": "fault_nodes_count",
        "description": "故障节点数",
        "query": 'count(kube_node_labels{label_dc_com_osm_nodepool_type="fault"})'
    },
    {
        "name": "gpu_fallen_count",
        "description": "GPU掉卡数",
        "query": 'count(gpu_job_info{job="node-exporter",gpu_status="fallen"})'
    }
]

for item in bigscreen_metrics_config_data:
    item["id"] = uuid.uuid4().hex
    bigscreen_metrics_config_info = BigscreenMetricsConfig(**item)
    BigscreenSQL.create_bigscreen_metrics_config(bigscreen_metrics_config_info)
