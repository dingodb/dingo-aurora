# 常量的类

# excel的目录文件
EXCEL_TEMP_DIR = "/home/dingoops/temp_excel/"
# 资产-服务器模板文件
ASSET_SERVER_TEMPLATE_FILE_DIR = "/api/template/server_template.xlsx"
# 资产-网络模板文件
ASSET_NETWORK_TEMPLATE_FILE_DIR = "/api/template/network_template.xlsx"
# 资产-网络流入流出模板文件
ASSET_NETWORK_FLOW_TEMPLATE_FILE_DIR = "/api/template/network_flow_template.xlsx"
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
asset_position_info_columns = {"cabinet_position":"机柜","u_position":"U位"}
# 资产设备合同信息列名对应表的列
asset_contract_info_columns = {"contract_number":"合同号","purchase_date":"购买日期","batch_number":"批次"}
# 资产设备归属信息列名对应表的列
asset_belong_info_columns = {"department_name":"部门","user_name":"负责人"}
# 资产设备租户信息列名对应表的列
asset_customer_info_columns = {"customer_name":"客户信息","rental_duration":"出租时长"}
# 资产设备配件信息列名对应表的列
asset_part_info_columns = {"cpu":"CPU","cpu_cores":"逻辑核心数量","memory":"内存","disk":"硬盘","raid":"RAID","nic":"网卡","gpu":"GPU","ib_card":"IB卡"}
# 资产-网络设备基础信息列名对应表的列
asset_network_basic_info_columns = {"asset_name":"设备名称","asset_type":"设备类型","equipment_number":"设备型号","asset_number":"资产编号"}
asset_network_basic_info_extra_columns = {"host_name":"主机名","manage_address":"管理地址","external_gateway":"带外网关","m_lagmac":"m-lag mac","network_equipment_role":"网络设备角色","serial_number":"序号","loopback":"loopback","vlanifv4":"vlanifv4","bgp_as":"BGP_AS","use_to":"用途"}
# 资产-网络设备厂商信息列名对应表的列
asset_network_manufacture_info_columns = {"name":"设备厂商"}
# 资产-网络设备位置信息列名对应表的列
asset_network_position_info_columns = {"cabinet_position":"机柜","u_position":"U位"}
# 资产-网络设备合同信息列名对应表的列
asset_network_contract_info_columns = {"contract_number":"采购合同号"}
# 资产-网络设备流信息列名对应表的列
asset_network_flow_info_columns = {"asset_name":"设备名称","cabinet_position":"机柜","u_position":"U位","port":"端口","opposite_asset_name":"对端设备名称","opposite_cabinet_position":"对端机柜","opposite_u_position":"对端U位","opposite_port":"对端端口","cable_type":"线缆类型","cable_interface_type":"线缆接口类型","cable_length":"线缆长度","label":"标签","opposite_label":"对端标签","description":"备注"}
# websocket目前接受的数据类型
websocket_data_type = {"big_screen"}
