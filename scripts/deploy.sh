#!/bin/bash

harbor_url=${1:-"docker.io/dongshany"}
node_port=${2:-"8887"}

image_version=${4:-"latest"}
module_name=${5:-"dingoops"}


echo "===========harbor_url: ${harbor_url}"
echo "===========node_port: ${node_port}"
echo "===========image_version: ${image_version}"
echo "===========module_name: ${module_name}"


echo "拉取最新的镜像"
docker pull ${harbor_url}/${module_name}:${image_version}
echo "开始检查并移除旧的容器"
if [[ -n "$(docker ps -f "name=${module_name}$" -f "status=running" -q )" ]]; then
  printf "停止容器: "
  docker stop $module_name
fi

# 若容器存在，则删除
if [[ -n "$(docker ps -a -f "name=${module_name}$"  -q )" ]]; then
  printf "删除容器: "
  docker rm $module_name
fi

# 判断是否存在 /etc/kolla/dingoops 目录，没有则创建
if [[ ! -d "/etc/kolla/dingoops" ]]; then
  mkdir -p /etc/kolla/dingoops
fi

docker_command="docker run -d -p ${node_port}:${node_port} -v /etc/kolla/dingoops:/etc/dingoops"
docker_command="${docker_command} -e TZ=Asia/Shanghai"
docker_command="${docker_command} --name ${module_name} ${harbor_url}/${module_name}:${image_version}"



printf "要执行的命令为:\n${docker_command}\n"
container_id=$(eval ${docker_command})

result=$(docker inspect -f {{.State.Running}} ${container_id})
if [[ "$result" = true ]]; then
  printf "\033[32m$module_name对应的容器启动成功,容器id为${container_id:0:12}\033[0m\n"
else
  printf "\033[31m$module_name对应的容器启动失败,容器id为${container_id:0:12}!\033[0m\n"
  exit 1
fi