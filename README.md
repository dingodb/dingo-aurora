# dingoOps


#### 本地调试
启动交互式命令行
```shell
$ export PYTHONSTARTUP=.python_startup.py
$ python3
```
curl -g -i -X POST http://10.220.58.248:8774/v2.1/servers \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -H "User-Agent: python-novaclient" \
  -H "X-Auth-Token: gAAAAABnpaufZlVeBIKeZYzFzCRjRMAc6wW7gOQaP4drEhkurZWACQdJUX3TV2PM4xGL9puh8I8Vb_ov6z_ceV4WhuoDgVIhyQgMokDorQRpDPsyMKt6-m8Bz4VXtZcgr2ZUkoHx5EhSJLkeYFAwWmcfQpVWRABZblcmnqeVJzxi0CHO8jIkVDg" \
  -H "X-OpenStack-Nova-API-Version: 2.1" \
  -d '{
    "server": {
        "config_drive": true,
        "flavorRef": "d79f8375-7387-457f-90d6-93eb1e073d0b",
        "imageRef": "acc3cf33-2329-4f6a-a470-1147a486e5da",
        "key_name": "cluster-api",
        "metadata": {
            "depends_on": " 33e1fd4f-c277-4e6a-8b48-ab637f7bcce6",
            "kubespray_groups": "kube_node,k8s_cluster,",
            "ssh_user": "root",
            "use_access_ip": "1"
        },
        "name": "dsy-test-11",
        "networks": [
            {
                "uuid": "4700f790-0a34-4ca2-a53d-f1438568f8ff"
            }
        ]
    }
}'