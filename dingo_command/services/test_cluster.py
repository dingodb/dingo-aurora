import unittest
from unittest.mock import patch, MagicMock
import logging
from dingo_command.services.cluster import ClusterService
from dingo_command.api.model.cluster import ClusterObject, NodeConfigObject, NetworkConfigObject, ClusterTFVarsObject, NodeGroup
import json

class TestClusterService(unittest.TestCase):
    def setUp(self):
        self.cluster_service = ClusterService()
        # Create a test cluster object
        self.cluster = ClusterObject(
            id="new-cluster-id",
            name="test-cluster",
            node_count=3,
            node_config=[
                NodeConfigObject(role="master", type="vm", flavor_id="m1.large", count=1, image="ubuntu-20.04"),
                NodeConfigObject(role="worker", type="vm", flavor_id="m1.medium", count=2, image="ubuntu-20.04")
            ],
            network_config=NetworkConfigObject(
                admin_network_id="net-123",
                pod_cidr="10.0.0.0/24",
                router_id="router-123",
                admin_subnet_id="subnet-123",
                bus_network_id="bus-network-123",
                bus_subnet_id="bus-network-123"
                
            )
        )


    def test_create_cluster_success(self):
        # Configure mocks

        mock_task = MagicMock()
        cluster_json_str = json.dumps(self.cluster.__dict__, default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o))
        # Call the method
        result = self.cluster_service.create_cluster(self.cluster)

        # Assertions
        self.assertEqual(result, "new-cluster-id")

    def test_list_clusters(self):
        # Configure mocks
        #构建查询参数
        query_params = {
            "id": None,
            "name": None,
            "type": None
        }
        result2 = self.cluster_service.list_clusters(query_params, 1, -1, None, None)
        print(result2)
        # First arg should be a ClusterTFVarsObject

    @patch('dingo_command.services.cluster.neutron')
    @patch('dingo_command.services.cluster.AssetSQL')
    @patch.object(ClusterService, 'convert_clusterinfo_todb')
    def test_create_cluster_exception(self, mock_convert, mock_asset_sql, mock_neutron):
        # Configure mocks to raise an exception
        mock_convert.side_effect = Exception("Test exception")

        # Call the method and check if it raises the exception
        with self.assertRaises(Exception):
            self.cluster_service.create_cluster(self.cluster)

    @patch('dingo_command.services.cluster.neutron')
    @patch('dingo_command.services.cluster.celery_app')
    @patch('dingo_command.services.cluster.AssetSQL')
    @patch.object(ClusterService, 'convert_clusterinfo_todb')
    def test_generate_k8s_nodes(self, mock_convert, mock_asset_sql, mock_celery, mock_neutron):
        # Configure mocks
        mock_convert.return_value = {"cluster_data": "test"}
        mock_asset_sql.create_cluster.return_value = "new-cluster-id"
        mock_neutron.list_external_networks.return_value = "external-net"
        mock_task = MagicMock()
        mock_celery.send_task.return_value = mock_task

        # Create empty dicts to test k8s node generation
        k8s_masters = {}
        k8s_nodes = {}
        
        # Call the method
        self.cluster_service.generate_k8s_nodes(self.cluster, k8s_masters, k8s_nodes)
        
        # Verify node creation
        self.assertEqual(len(k8s_masters), 1)
        self.assertEqual(len(k8s_nodes), 2)
        self.assertTrue("master-1" in k8s_masters)
        self.assertTrue("node-1" in k8s_nodes)
        self.assertTrue("node-2" in k8s_nodes)
        
        # Verify node properties
        self.assertTrue(k8s_masters["master-1"].floating_ip)
        self.assertTrue(k8s_masters["master-1"].etcd)
        self.assertEqual(k8s_masters["master-1"].flavor_id, "m1.large")
        self.assertEqual(k8s_masters["master-1"].az, "nova")

if __name__ == '__main__':
    unittest.main()