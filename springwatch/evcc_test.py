import unittest
from unittest.mock import patch, Mock
from springwatch.evcc import EvccClient
from springwatch.model import WorldView


class TestEvccClient(unittest.TestCase):

    def setUp(self):
        self.evcc_client = EvccClient("http://localhost:7070", 1)
        self.world = WorldView()

    @patch('springwatch.evcc.requests.get')
    def test_load_state_old_format_with_result_wrapper(self, mock_get):
        """Test that the client works with the old API format (with 'result' wrapper)"""
        # Mock response with old format
        mock_response = Mock()
        mock_response.json.return_value = {
            "result": {
                "loadpoints": [
                    {"enabled": True, "charging": False}
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        state = self.evcc_client.load_state()

        self.assertIn("loadpoints", state)
        self.assertEqual(state["loadpoints"][0]["enabled"], True)
        self.assertEqual(state["loadpoints"][0]["charging"], False)

    @patch('springwatch.evcc.requests.get')
    def test_load_state_new_format_without_result_wrapper(self, mock_get):
        """Test that the client works with the new API format (without 'result' wrapper)"""
        # Mock response with new format
        mock_response = Mock()
        mock_response.json.return_value = {
            "loadpoints": [
                {"enabled": False, "charging": True}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        state = self.evcc_client.load_state()

        self.assertIn("loadpoints", state)
        self.assertEqual(state["loadpoints"][0]["enabled"], False)
        self.assertEqual(state["loadpoints"][0]["charging"], True)

    @patch('springwatch.evcc.requests.get')
    def test_update_with_old_format(self, mock_get):
        """Test that the update method works correctly with old API format"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "result": {
                "loadpoints": [
                    {"enabled": True, "charging": True}
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        self.evcc_client.update(self.world)

        self.assertTrue(self.world.charging_enabled)
        self.assertTrue(self.world.is_charging)

    @patch('springwatch.evcc.requests.get')
    def test_update_with_new_format(self, mock_get):
        """Test that the update method works correctly with new API format"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "loadpoints": [
                {"enabled": False, "charging": False}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        self.evcc_client.update(self.world)

        self.assertFalse(self.world.charging_enabled)
        self.assertFalse(self.world.is_charging)


if __name__ == '__main__':
    unittest.main()
