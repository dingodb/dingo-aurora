import unittest
from unittest.mock import MagicMock, patch

from dingoops.utils.neutron import API as neutron
from services import CONF


class TestNeutron(unittest.TestCase):

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
        
    def test_list_external_networks_with_client(self):

        
        # 创建模拟的neutron客户端
        mock_client = neutron.get_neutron_client(CONF)
        
        # 调用被测试的函数并传入客户端
        result = neutron.list_external_networks(neutron_client=mock_client)
        
        # 验证结果
    
    @patch('dingoops.utils.neutron.get_neutron_client')
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
    
    @patch('dingoops.utils.neutron.get_neutron_client')
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