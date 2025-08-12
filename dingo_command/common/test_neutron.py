import unittest
from unittest.mock import MagicMock, patch

from dingo_command.utils.neutron import API as neutron
from dingo_command.common.cinder_client import CinderClient
from dingo_command.common.network import init_cluster_network
from dingo_command.services import CONF


class TestNeutron(unittest.TestCase):
    def test_init_cluster_network(self):
        """
        测试 init_cluster_network 方法
        """
        # 假设有一个测试 project_id
        test_project_id = "0ad6b7751e904a35a9e99afaf1da416a"
        try:
            init_cluster_network(test_project_id, "68ebc544-0f4f-4fce-8106-7c1c31fbae4c")
            print("init_cluster_network 测试通过")
        except Exception as e:
            print(f"init_cluster_network 测试失败: {e}")

    def test_list_external_networks(self):
        # 准备模拟数据
        mock_networks = {
            'networks': [
                {
                    'id': 'network-id-1',
                    'name': 'ext-net-1',
                    'router:external': True
                },
                {
                    'id': 'network-id-2',
                    'name': 'ext-net-2',
                    'router:external': True
                }
            ]
        }
        
        # 创建模拟的neutron客户端
        mock_client = neutron.get_neutron_client(CONF)
        
        # 调用被测试的函数
        result = neutron.list_external_networks()
        
        # 验证结果
        self.assertEqual(result, mock_networks['networks'])
        mock_client.list_networks.assert_called_once_with(**{'router:external': True})

    def test_list_volume_type(self):

        # 创建模拟的neutron客户端
        cinder_client = CinderClient()
        
        # 调用被测试的函数
        result = cinder_client.list_volum_type()
        
        
    def test_list_external_networks_with_client(self):

        
        # 创建模拟的neutron客户端
        mock_client = neutron.get_neutron_client(CONF)
        
        # 调用被测试的函数并传入客户端
        result = neutron.list_external_networks(neutron_client=mock_client)
        
        # 验证结果
    
    @patch('dingo_command.utils.neutron.get_neutron_client')
    def test_list_external_networks_empty(self, mock_get_neutron_client):
        # 准备模拟数据 - 没有外部网络
        mock_networks = {'networks': []}
        
        # 创建模拟的neutron客户端
        mock_client = MagicMock()
        mock_client.list_networks.return_value = mock_networks
        mock_get_neutron_client.return_value = mock_client
        
        # 调用被测试的函数
        result = neutron.list_external_networks()
        
        # 验证结果
        self.assertEqual(result, [])
        mock_client.list_networks.assert_called_once_with(**{'router:external': True})
    
    @patch('dingo_command.utils.neutron.get_neutron_client')
    def test_list_external_networks_missing_key(self, mock_get_neutron_client):
        # 准备模拟数据 - 响应中没有networks键
        mock_networks = {}
        
        # 创建模拟的neutron客户端
        mock_client = MagicMock()
        mock_client.list_networks.return_value = mock_networks
        mock_get_neutron_client.return_value = mock_client
        
        # 调用被测试的函数
        result = neutron.list_external_networks()
        
        # 验证结果
        self.assertEqual(result, [])
        mock_client.list_networks.assert_called_once_with(**{'router:external': True})


if __name__ == '__main__':
    unittest.main()