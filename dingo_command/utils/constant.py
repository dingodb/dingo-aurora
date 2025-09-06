# 常量的类
import uuid

# k8s kubeconfig指定存放目录
KUBECONFIG_DIR_DEFAULT = "/home/dingo-command/kubeconfig/"
#容器实例命名空间前缀
NAMESPACE_PREFIX = "ns-"
#用户公钥存放configmap的前缀
CONFIGMAP_PREFIX = "cm-ssh-key-"
#容器实例系统盘默认挂载路径
AI_INSTANCE_SYSTEM_MOUNT_PATH_DEFAULT = "/root/public-system/"
#容器实例PVC默认挂载路径
AI_INSTANCE_PVC_MOUNT_PATH_DEFAULT="/root/pvc"
#容器实例ssh公钥configMap默认挂载路径
AI_INSTANCE_CM_MOUNT_PATH_SSHKEY="/root/.ssh/authorized_keys"
AI_INSTANCE_CM_MOUNT_PATH_SSHKEY_SUB_PATH="authorized_keys"
#容器实例系统盘默认名称
SYSTEM_DISK_NAME_DEFAULT = "system-disk"
#容器实例系统盘默认大小
SYSTEM_DISK_SIZE_DEFAULT = "50Gi"
#资源类型
RESOURCE_TYPE_KEY = "dc.com/product.item"
PRODUCT_TYPE_CCI = "CCI"
APP_LABEL = "app"
#jupyter开发工具
DEV_TOOL_JUPYTER = "jupyter"
#CCI保存为镜像后缀
SAVE_TO_IMAGE_CCI_SUFFIX = "_saving_to_image_cci"

# excel的目录文件
EXCEL_TEMP_DIR = "/home/dingo_command/temp_excel/"
# 资产-服务器模板文件
ASSET_SERVER_TEMPLATE_FILE_DIR = "/dingo_command/api/template/server_template.xlsx"
# 资产-网络模板文件
ASSET_NETWORK_TEMPLATE_FILE_DIR = "/dingo_command/api/template/network_template.xlsx"
# 资产-网络流入流出模板文件
ASSET_NETWORK_FLOW_TEMPLATE_FILE_DIR = "/dingo_command/api/template/network_flow_template.xlsx"
# 计费汇总模板文件
RATING_SUMMARY_TEMPLATE_FILE_DIR = "/dingo_command/api/template/rating_summary_template.xlsx"
# 导入的资产设备类型
ASSET_TEMPLATE_ASSET_TYPE = ("server", "network", "network_flow")
# 资产设备sheet页名称
ASSET_TEMPLATE_ASSET_SHEET = "asset"
# 资产配件sheet页名称
ASSET_TEMPLATE_PART_SHEET = "part"
# 资产网络sheet页名称
ASSET_TEMPLATE_NETWORK_SHEET = "network"

# 资产设备状态 0：空闲、1：备机、2：分配、3：故障
asset_status_dict = ([(0, "空闲"), (0, "备机"), (2, "分配"), (3, "故障")])

# 资产设备模板字段列
asset_equipment_columns =("机架","机柜","U位","设备名称","设备型号","资产编号","序列号","部门","负责人","主机名","IP","IDRAC","用途","密码","操作系统","购买日期","厂商","批次","备注")
# 资产设备基础信息列名对应表的列
asset_basic_info_columns = {"asset_name":"设备名称","asset_type":"设备类型","equipment_number":"设备型号","sn_number":"序列号","asset_number":"资产编号","asset_description":"备注"}
asset_basic_info_extra_columns = {"host_name":"主机名","ip":"IP","idrac":"IDRAC","use_to":"用途","operate_system":"操作系统"}
# 资产设备厂商信息列名对应表的列
asset_manufacture_info_columns = {"name":"厂商"}
# 资产设备位置信息列名对应表的列
asset_position_info_columns = {"frame_position":"机房号","cabinet_position":"机柜","u_position":"U位"}
# 资产设备合同信息列名对应表的列
asset_contract_info_columns = {"contract_number":"采购合同编号","purchase_date":"购买日期","batch_number":"批次"}
# 资产设备归属信息列名对应表的列
asset_belong_info_columns = {"department_name":"部门","user_name":"负责人"}
# 资产设备租户信息列名对应表的列
asset_customer_info_columns = {"customer_name":"客户信息","rental_duration":"出租时长"}
# 资产设备配件信息列名对应表的列
asset_part_info_columns = {"cpu":"CPU","cpu_cores":"逻辑核心数量","memory":"内存","disk":"系统盘","data_disk":"数据盘","nic":"网卡","gpu":"GPU","ib_card":"IB卡","module":"模块","part_update":"配件变更"}
# 资产-网络设备基础信息列名对应表的列
asset_network_basic_info_columns = {"asset_name":"设备名称","asset_type":"设备类型","equipment_number":"设备型号","asset_number":"资产编号"}
asset_network_basic_info_extra_columns = {"host_name":"主机名","manage_address":"管理地址","external_gateway":"带外网关","m_lagmac":"m-lag mac","network_equipment_role":"网络设备角色","serial_number":"序号","loopback":"loopback","vlanifv4":"vlanifv4","bgp_as":"BGP_AS","use_to":"用途"}
# 资产-网络设备厂商信息列名对应表的列
asset_network_manufacture_info_columns = {"name":"设备厂商"}
# 资产-网络设备位置信息列名对应表的列
asset_network_position_info_columns = {"frame_position":"机房号","cabinet_position":"机柜","u_position":"U位"}
# 资产-网络设备合同信息列名对应表的列
asset_network_contract_info_columns = {"contract_number":"采购合同编号"}
# 资产-网络设备流信息列名对应表的列
asset_network_flow_info_columns = {"asset_name":"设备名称","cabinet_position":"机柜","u_position":"U位","port":"端口","opposite_asset_name":"对端设备名称","opposite_cabinet_position":"对端机柜","opposite_u_position":"对端U位","opposite_port":"对端端口","cable_type":"线缆类型","cable_interface_type":"线缆接口类型","cable_length":"线缆长度","label":"标签","opposite_label":"对端标签","description":"备注"}
BINDING_PROFILE = 'binding:profile'

# websocket目前接受的数据类型
websocket_data_type = {"big_screen"}

# websocket的频道以及与数据类型的对应关系
websocket_channels = ["dingoOps:big_screen_websocket_channel"]
websocket_type_channels = {"big_screen":"dingoOps:big_screen_websocket_channel"}
asset_part_type_dict = ["cpu","cpu_cores","data_disk","disk","gpu","ib_card","memory","module","nic","part_update"]

# mq的配置信息
MQ_MANAGE_PORT = "15672"
MQ_PORT = 5672
MQ_SHOVEL_ADD_URL = "/api/parameters/shovel/%2F/"
# rabbitmq的所有shovel和queue的关系
RABBITMQ_SHOVEL_QUEUE = {"dingo_command_external_message_shovel":"dingo_command_external_message_queue"}
RABBITMQ_EXTERNAL_MESSAGE_QUEUE = "dingo_command_external_message_queue"
# message类型和dingodb表的对应关系
MESSAGE_TYPE_TABLE = {
    "Report_Storage": "bsm_dws_storage_capacity_consume_info",
    "Report_Share_Bandwidth": "bsm_dws_share_bandwidth_consume_info",
    "Report_Exclusive_Bandwidth": "bsm_dws_exclusive_bandwidth_consume_info",
    "Report_Gpu_Card_Allocate_Detail": "bsm_dwd_gpu_card_allocate_detail_info",
    "Report_Gpu_Card_Allocate": "bsm_dws_gpu_card_allocate_info",
    "Report_Gpu_Consume_Category_Detail": "bsm_dwd_gpu_consume_category_detail_info",
    "Report_Gpu_Consume_Card_Detail": "bsm_dwd_gpu_consume_card_detail_info",
    "Report_Gpu_Consume": "bsm_dws_gpu_consume_info",
    "Report_Gpu_Avg_Allocate": "bsm_dws_gpu_avg_allocate_info",
    "Report_Gpu_Avg_Consume": "bsm_dws_gpu_avg_consume_info",
    "Report_Dwd_Node_Detail": "bsm_dwd_node_detail_info",
    "Report_Dwd_Pod_Detail": "bsm_dwd_pod_detail_info",
    "Report_Dwd_Node_Detail_Five_Minutes": "bsm_dwd_node_detail_info_five_minutes",
    "Report_Dwd_Pod_Detail_Five_Minutes": "bsm_dwd_pod_detail_info_five_minutes",
    "Report_Dwd_Tenant_Bandwidth_Detail": "bsm_dwd_tenant_bandwidth_detail_info",
    "Report_Dwd_Operator_Bandwidth_Detail": "bsm_dwd_operator_bandwidth_detail_info",
}

GPU_CARD_MAPPING = {
    "NVIDIA-H800A-NV-80G": {
        "original_name": "NVIDIA-H100-80GB-HBM3",
        "gpu_code": "nvidia.com/gpu-h100-80gb-hbm3"
    },
    "NVIDIA-H800A-NV-96G": {
        "original_name": "NVIDIA-H100",
        "gpu_code": "nvidia.com/gpu-h100"
    },
    "NVIDIA-L40S-PCIE-48G": {
        "original_name": "NVIDIA-L40S",
        "gpu_code": "nvidia.com/gpu-l40s"
    },
    "NVIDIA-H800-NV-80G": {
        "original_name": "NVIDIA-H800",
        "gpu_code": "nvidia.com/gpu-h800"
    },
    "NVIDIA-H800E-NV-141G": {
        "original_name": "NVIDIA-H200",
        "gpu_code": "nvidia.com/gpu-h200"
    },
    "NVIDIA-H800E-NV-35G": {
        "original_name": "NVIDIA-H200-MIG",
        "gpu_code": "nvidia.com/mig-h200-1g.35gb"
    }
}