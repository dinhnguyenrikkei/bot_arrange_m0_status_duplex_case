import unittest
from unittest import mock
import os
import tempfile
import config as config_manager
import config

class TestConfigManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary file to act as the .env file
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, mode="w+", suffix=".env")
        self.temp_file_path = self.temp_file.name
        self.temp_file.close()
        
        # Patch the ENV_FILE_PATH in config_manager
        self.original_env_path = config_manager.ENV_FILE_PATH
        config_manager.ENV_FILE_PATH = self.temp_file_path
        
    def tearDown(self):
        # Restore the original ENV_FILE_PATH
        config_manager.ENV_FILE_PATH = self.original_env_path
        # Clean up temporary file
        if os.path.exists(self.temp_file_path):
            os.remove(self.temp_file_path)

    def test_get_current_env_values_defaults_or_config(self):
        # Delete the temp file to simulate non-existing .env file
        if os.path.exists(self.temp_file_path):
            os.remove(self.temp_file_path)
            
        values = config_manager.get_current_env_values()
        
        # Verify it returns values from config fallback
        self.assertEqual(values["LARK_APP_ID"], config.LARK_APP_ID)
        self.assertEqual(values["MAX_ASSIGNMENTS_PER_DAY"], str(config.MAX_ASSIGNMENTS_PER_DAY))
        self.assertEqual(values["COOLDOWN_MINUTES_BETWEEN_CALLS"], str(config.COOLDOWN_MINUTES_BETWEEN_CALLS))
        self.assertEqual(values["SYNC_INTERVAL_SECONDS"], str(config.SYNC_INTERVAL_SECONDS))

    def test_get_current_env_values_from_file(self):
        # Write mock data to the temp .env file
        with open(self.temp_file_path, "w", encoding="utf-8") as f:
            f.write("# This is a comment\n")
            f.write("LARK_APP_ID=\"env_mock_app_id\"\n")
            f.write("LARK_APP_SECRET = env_mock_secret\n")
            f.write("MAX_ASSIGNMENTS_PER_DAY='5'\n")
            f.write("SYNC_INTERVAL_SECONDS='120'\n")
            
        values = config_manager.get_current_env_values()
        
        self.assertEqual(values["LARK_APP_ID"], "env_mock_app_id")
        self.assertEqual(values["LARK_APP_SECRET"], "env_mock_secret")
        self.assertEqual(values["MAX_ASSIGNMENTS_PER_DAY"], "5")
        self.assertEqual(values["SYNC_INTERVAL_SECONDS"], "120")
        # Unspecified keys should fall back to empty string or default defined in config_manager
        self.assertEqual(values["COOLDOWN_MINUTES_BETWEEN_CALLS"], "30")

    def test_update_env_values(self):
        # Pre-populate temp file with some keys
        with open(self.temp_file_path, "w", encoding="utf-8") as f:
            f.write("LARK_APP_ID=\"old_id\"\n")
            f.write("LARK_BASE_TOKEN=\"old_token\"\n")
            
        new_values = {
            "LARK_APP_ID": "new_id",
            "LARK_APP_SECRET": "new_secret",
            "MAX_ASSIGNMENTS_PER_DAY": "10",
            "SYNC_INTERVAL_SECONDS": "45"
        }
        
        # Run update
        config_manager.update_env_values(new_values)
        
        # Read back using config_manager
        values = config_manager.get_current_env_values()
        
        self.assertEqual(values["LARK_APP_ID"], "new_id")
        self.assertEqual(values["LARK_APP_SECRET"], "new_secret")
        self.assertEqual(values["LARK_BASE_TOKEN"], "old_token")
        self.assertEqual(values["MAX_ASSIGNMENTS_PER_DAY"], "10")
        self.assertEqual(values["SYNC_INTERVAL_SECONDS"], "45")
        
        # Verify globals in config were reloaded
        self.assertEqual(config.LARK_APP_ID, "new_id")
        self.assertEqual(config.LARK_APP_SECRET, "new_secret")
        self.assertEqual(config.MAX_ASSIGNMENTS_PER_DAY, 10)
        self.assertEqual(config.SYNC_INTERVAL_SECONDS, 45)

    @unittest.mock.patch('requests.post')
    @unittest.mock.patch('requests.get')
    def test_update_env_values_auto_discover(self, mock_get, mock_post):
        # Mock token fetch
        mock_post.return_value.json.return_value = {
            "code": 0,
            "tenant_access_token": "mock_tenant_token"
        }
        
        # Mock list tables
        mock_get.return_value.json.return_value = {
            "code": 0,
            "data": {
                "items": [
                    {"name": "Customer 2024 (Tiktok)", "table_id": "tblTiktokDiscovered"},
                    {"name": "Tư vấn viên (TVV)", "table_id": "tblTvvDiscovered"}
                ]
            }
        }
        
        new_values = {
            "LARK_APP_ID": "mock_app_id",
            "LARK_APP_SECRET": "mock_secret",
            "LINK_TABLE_TIKTOK": "https://rjptqxrx86i6.jp.larksuite.com/base/basTikTok123",
            "LINK_TABLE_TVV": "https://rjptqxrx86i6.jp.larksuite.com/base/basTvv123",
            "COOLDOWN_MINUTES_BETWEEN_CALLS": "30"
        }
        
        config_manager.update_env_values(new_values)
        
        values = config_manager.get_current_env_values()
        
        # Verify tokens and auto-discovered table IDs were correctly set
        self.assertEqual(values["LARK_BASE_TOKEN"], "basTikTok123")
        self.assertEqual(values["TABLE_TIKTOK_ID"], "tblTiktokDiscovered")
        self.assertEqual(values["LARK_BASE_TOKEN_TVV"], "basTvv123")
        self.assertEqual(values["TABLE_TVV_ID"], "tblTvvDiscovered")

    def test_update_env_values_sheets_url(self):
        new_values = {
            "LINK_TABLE_TIKTOK": "https://rjptqxrx86i6.jp.larksuite.com/sheets/shtTikTokabc?table=tblTikTokxyz",
            "LINK_TABLE_TVV": "https://rjptqxrx86i6.jp.larksuite.com/sheets/shtTvvabc?table=tblTvvxyz",
        }
        config_manager.update_env_values(new_values)
        values = config_manager.get_current_env_values()
        
        self.assertEqual(values["LARK_BASE_TOKEN"], "shtTikTokabc")
        self.assertEqual(values["TABLE_TIKTOK_ID"], "tblTikTokxyz")
        self.assertEqual(values["LARK_BASE_TOKEN_TVV"], "shtTvvabc")
        self.assertEqual(values["TABLE_TVV_ID"], "tblTvvxyz")

if __name__ == "__main__":
    unittest.main()
