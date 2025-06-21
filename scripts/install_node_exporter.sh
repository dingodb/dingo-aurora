#!/bin/bash

# Node Exporter 安装脚本
set -e

# 配置参数
PUSH_GATEWAY_URL="http://pushgateway:9092"
NODE_EXPORTER_VERSION="1.9.1"
DOWNLOAD_URL="https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz"
INSTALL_DIR="/opt/node_exporter"
SERVICE_FILE="/etc/systemd/system/node_exporter.service"
JOB_FILE="/etc/systemd/system/pushgateway-job.service"
TIMER_FILE="/etc/systemd/system/pushgateway-job.timer"


# 创建安装目录
echo "创建安装目录: ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

# 下载并解压node_exporter
echo "下载 node_exporter v${NODE_EXPORTER_VERSION}..."
wget -q --show-progress "${DOWNLOAD_URL}" -O /tmp/node_exporter.tar.gz

echo "解压文件..."
tar xzf /tmp/node_exporter.tar.gz -C /tmp/

# 复制文件到安装目录
echo "安装文件到 ${INSTALL_DIR}..."
cp "/tmp/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter" "${INSTALL_DIR}/"
chown -R root:root "${INSTALL_DIR}"
chmod +x "${INSTALL_DIR}/node_exporter"

# 清理临时文件
echo "清理临时文件..."
rm -rf /tmp/node_exporter.tar.gz /tmp/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64

# 创建系统服务
echo "创建系统服务..."
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Node Exporter
After=network.target

[Service]
User=root
ExecStart=${INSTALL_DIR}/node_exporter
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 重新加载systemd并启动服务
echo "重新加载systemd配置..."
systemctl daemon-reload
echo "启动node_exporter服务..."
systemctl start node_exporter
systemctl enable node_exporter

# 显示服务状态
echo "node_exporter服务状态:"
systemctl status node_exporter --no-pager

# 安装定时服务
cat > "${JOB_FILE}" <<EOF
[Unit]
Description=Push metrics to Pushgateway
After=network.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c '/usr/bin/curl -s http://localhost:9100/metrics | /usr/bin/curl --data-binary @- "${PUSH_GATEWAY_URL}/metrics/job/vm/instance/%H"'
Restart=on-failure
EOF



cat > "${TIMER_FILE}" <<EOF
[Unit]
Description=Timer for pushing metrics to Pushgateway

[Timer]
OnUnitActiveSec=60s
AccuracySec=1s
Persistent=true

[Install]
WantedBy=timers.target
EOF


systemctl daemon-reload
systemctl start pushgateway-job.service 
systemctl start pushgateway-job.timer
systemctl enable pushgateway-job.timer



echo -e "\n安装完成！node_exporter 已成功安装并运行。"
echo "访问地址: http://$(hostname -I | awk '{print $1}'):9100/metrics"