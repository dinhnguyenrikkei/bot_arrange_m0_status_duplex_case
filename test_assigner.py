import unittest
from unittest.mock import MagicMock
import time
from datetime import datetime, timezone, timedelta

# Import modules from our project
import config
# Set test configs before importing other modules
config.LARK_APP_ID = "test_app_id"
config.LARK_APP_SECRET = "test_app_secret"
config.LARK_BASE_TOKEN = "test_base_token"
config.TABLE_TIKTOK_ID = "test_tiktok_table"
config.TABLE_TVV_ID = "test_tvv_table"
config.MAX_ASSIGNMENTS_PER_DAY = 2
config.COOLDOWN_MINUTES_BETWEEN_CALLS = 30

from assigner import (
    check_tvv_availability,
    assign_m0_lead_to_tvv,
    assign_t0_leads_to_tts,
    get_today_range,
    tz_vietnam
)
from lark_client import LarkClient

class TestLeadAssignment(unittest.TestCase):
    
    def setUp(self):
        # Create a mock Lark client
        self.client = MagicMock(spec=LarkClient)
        
    def test_today_range(self):
        start, end = get_today_range()
        self.assertTrue(start < end)
        # Ensure it represents roughly 24 hours
        diff_hours = (end - start) / (1000 * 60 * 60)
        self.assertAlmostEqual(diff_hours, 24.0, delta=0.1)

    def test_check_tvv_availability(self):
        # TVV is busy if they have a callback within 30 minutes of the target callback time.
        target_time = 1716200000000 # 2026-05-20 approx.
        cooldown_ms = 30 * 60 * 1000
        
        # Test case 1: No previous assignments today -> Should be Free
        self.assertTrue(check_tvv_availability("user_1", target_time, []))
        
        # Test case 2: Previous assignment with callback at the exact same time -> Should be Busy
        assignments = [
            {"assigned_user_id": "user_1", "callback_time": target_time, "assigned_time": int(time.time() * 1000)}
        ]
        self.assertFalse(check_tvv_availability("user_1", target_time, assignments))
        
        # Test case 3: Previous assignment is far away (e.g. 40 minutes before) -> Should be Free
        assignments = [
            {"assigned_user_id": "user_1", "callback_time": target_time - (40 * 60 * 1000), "assigned_time": int(time.time() * 1000)}
        ]
        self.assertTrue(check_tvv_availability("user_1", target_time, assignments))
        
        # Test case 4: Previous assignment is close (e.g. 20 minutes after) -> Should be Busy
        assignments = [
            {"assigned_user_id": "user_1", "callback_time": target_time + (20 * 60 * 1000), "assigned_time": int(time.time() * 1000)}
        ]
        self.assertFalse(check_tvv_availability("user_1", target_time, assignments))

        # Test case 5: Different user has a conflict -> User 1 should still be Free
        assignments = [
            {"assigned_user_id": "user_2", "callback_time": target_time, "assigned_time": int(time.time() * 1000)}
        ]
        self.assertTrue(check_tvv_availability("user_1", target_time, assignments))

    def test_assign_m0_lead_to_tvv_scenario_1_same_region_priority(self):
        """Scenario 1: Northern lead, active TVVs in North and South. Should pick North."""
        lead_id = "lead_001"
        lead_record = {
            "record_id": lead_id,
            "fields": {
                config.FIELD_TIKTOK_STATUS: "M0",
                config.FIELD_TIKTOK_REGION: "Miền Bắc",
                config.FIELD_TIKTOK_CALLBACK_TIME: 1716200000000
            }
        }
        self.client.get_record.return_value = lead_record
        
        # TVVs: TVV 1 (North), TVV 2 (South)
        tvvs_records = [
            {
                "record_id": "rec_tvv_1",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    config.FIELD_TVV_USER: [{"id": "user_north", "name": "TVV North"}]
                }
            },
            {
                "record_id": "rec_tvv_2",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Nam",
                    config.FIELD_TVV_USER: [{"id": "user_south", "name": "TVV South"}]
                }
            }
        ]
        self.client.list_records.side_effect = lambda table_id: tvvs_records if table_id == config.TABLE_TVV_ID else []
        
        # Act
        selected = assign_m0_lead_to_tvv(self.client, lead_id)
        
        # Assert
        self.assertIsNotNone(selected)
        self.assertEqual(selected["user_id"], "user_north")
        self.assertEqual(selected["name"], "TVV North")
        self.client.update_record.assert_called_once()
        
    def test_assign_m0_lead_to_tvv_scenario_2_round_robin_fairness(self):
        """Scenario 2: Both TVVs in North, but TVV 1 has 1 assignment today, TVV 2 has 0. Pick TVV 2."""
        lead_id = "lead_002"
        lead_record = {
            "record_id": lead_id,
            "fields": {
                config.FIELD_TIKTOK_STATUS: "M0",
                config.FIELD_TIKTOK_REGION: "Miền Bắc",
                config.FIELD_TIKTOK_CALLBACK_TIME: 1716200000000
            }
        }
        self.client.get_record.return_value = lead_record
        
        tvvs_records = [
            {
                "record_id": "rec_tvv_1",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    config.FIELD_TVV_USER: [{"id": "user_n1", "name": "North 1"}]
                }
            },
            {
                "record_id": "rec_tvv_2",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    config.FIELD_TVV_USER: [{"id": "user_n2", "name": "North 2"}]
                }
            }
        ]
        
        # Mock today's assignments: user_n1 already has 1 assignment today
        start_ms, _ = get_today_range()
        today_assignments_records = [
            {
                "record_id": "prev_lead",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_n1"}],
                    config.FIELD_TIKTOK_ASSIGNED_TIME: start_ms + 1000,
                    config.FIELD_TIKTOK_CALLBACK_TIME: start_ms + 10000
                }
            }
        ]
        
        def mock_list_records(table_id):
            if table_id == config.TABLE_TVV_ID:
                return tvvs_records
            elif table_id == config.TABLE_TIKTOK_ID:
                return today_assignments_records
            return []
            
        self.client.list_records.side_effect = mock_list_records
        
        # Act
        selected = assign_m0_lead_to_tvv(self.client, lead_id)
        
        # Assert
        self.assertIsNotNone(selected)
        self.assertEqual(selected["user_id"], "user_n2")  # Should pick user_n2 because they have 0 assignments
        
    def test_assign_m0_lead_to_tvv_scenario_3_overflow_to_other_region(self):
        """Scenario 3: North TVVs are busy (cooldown conflict). Should overflow to South TVV."""
        start_ms, _ = get_today_range()
        lead_id = "lead_003"
        lead_record = {
            "record_id": lead_id,
            "fields": {
                config.FIELD_TIKTOK_STATUS: "M0",
                config.FIELD_TIKTOK_REGION: "Miền Bắc",
                config.FIELD_TIKTOK_CALLBACK_TIME: start_ms + 10000
            }
        }
        self.client.get_record.return_value = lead_record
        
        tvvs_records = [
            {
                "record_id": "rec_tvv_1",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    config.FIELD_TVV_USER: [{"id": "user_n1", "name": "North 1"}]
                }
            },
            {
                "record_id": "rec_tvv_2",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Nam",
                    config.FIELD_TVV_USER: [{"id": "user_s1", "name": "South 1"}]
                }
            }
        ]
        
        # Mock today's assignments: North 1 (user_n1) has a conflicting callback at the target time
        today_assignments_records = [
            {
                "record_id": "l1",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_n1"}],
                    config.FIELD_TIKTOK_ASSIGNED_TIME: start_ms + 5000,
                    config.FIELD_TIKTOK_CALLBACK_TIME: start_ms + 10000
                }
            }
        ]
        
        def mock_list_records(table_id):
            if table_id == config.TABLE_TVV_ID:
                return tvvs_records
            elif table_id == config.TABLE_TIKTOK_ID:
                return today_assignments_records
            return []
            
        self.client.list_records.side_effect = mock_list_records
        
        # Act
        selected = assign_m0_lead_to_tvv(self.client, lead_id)
        
        # Assert
        self.assertIsNotNone(selected)
        self.assertEqual(selected["user_id"], "user_s1")  # Should overflow to South TVV (user_s1)

    def test_assign_t0_leads_to_tts(self):
        """Test that daily T0 lead distribution to active TTS is disabled and returns 0."""
        # Act
        assigned_count = assign_t0_leads_to_tts(self.client)
        
        # Assert
        self.assertEqual(assigned_count, 0)
        self.client.batch_update_records.assert_not_called()

    def test_assign_m0_lead_with_none_callback_time(self):
        """If a lead has no callback time, assign it to a TVV and write back the resolved time."""
        lead_id = "lead_none"
        lead_record = {
            "record_id": lead_id,
            "fields": {
                config.FIELD_TIKTOK_STATUS: "M0",
                config.FIELD_TIKTOK_REGION: "Miền Bắc",
                config.FIELD_TIKTOK_CALLBACK_TIME: None
            }
        }
        self.client.get_record.return_value = lead_record
        
        tvvs_records = [
            {
                "record_id": "rec_tvv_1",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    config.FIELD_TVV_USER: [{"id": "user_north", "name": "TVV North"}]
                }
            }
        ]
        self.client.list_records.side_effect = lambda table_id: tvvs_records if table_id == config.TABLE_TVV_ID else []
        
        # Act
        selected = assign_m0_lead_to_tvv(self.client, lead_id)
        
        # Assert
        self.assertIsNotNone(selected)
        self.assertEqual(selected["user_id"], "user_north")
        
        # Check update_record was called with the callback time populated
        self.client.update_record.assert_called_once()
        args = self.client.update_record.call_args[0]
        update_fields = args[2]
        self.assertIsNotNone(update_fields.get(config.FIELD_TIKTOK_CALLBACK_TIME))

    def test_assign_m0_lead_with_collision_does_not_shift_time(self):
        """If a TVV has a conflict, select the TVV and do NOT shift callback time (keep original)."""
        lead_id = "lead_clash"
        target_time = 1716200000000 # 2026-05-20 approx.
        lead_record = {
            "record_id": lead_id,
            "fields": {
                config.FIELD_TIKTOK_STATUS: "M0",
                config.FIELD_TIKTOK_REGION: "Miền Bắc",
                config.FIELD_TIKTOK_CALLBACK_TIME: target_time
            }
        }
        self.client.get_record.return_value = lead_record
        
        tvvs_records = [
            {
                "record_id": "rec_tvv_1",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    config.FIELD_TVV_USER: [{"id": "user_north", "name": "TVV North"}]
                }
            }
        ]
        
        # Mock today's assignments: TVV North has a call at target_time
        today_assignments_records = [
            {
                "record_id": "prev_l1",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_north"}],
                    config.FIELD_TIKTOK_ASSIGNED_TIME: int(time.time() * 1000),
                    config.FIELD_TIKTOK_CALLBACK_TIME: target_time
                }
            }
        ]
        
        def mock_list_records(table_id):
            if table_id == config.TABLE_TVV_ID:
                return tvvs_records
            elif table_id == config.TABLE_TIKTOK_ID:
                return today_assignments_records
            return []
            
        self.client.list_records.side_effect = mock_list_records
        
        # Act
        selected = assign_m0_lead_to_tvv(self.client, lead_id)
        
        # Assert
        self.assertIsNotNone(selected)
        self.assertEqual(selected["user_id"], "user_north")
        
        # Check update_record was called, and callback time was NOT modified (not in update_fields)
        self.client.update_record.assert_called_once()
        args = self.client.update_record.call_args[0]
        update_fields = args[2]
        self.assertNotIn(config.FIELD_TIKTOK_CALLBACK_TIME, update_fields)

    def test_normalize_region(self):
        from assigner import normalize_region
        self.assertEqual(normalize_region("Hà Nội"), "Miền Bắc")
        self.assertEqual(normalize_region("HCM"), "Miền Nam")
        self.assertEqual(normalize_region("hồ chí minh"), "Miền Nam")
        self.assertEqual(normalize_region("HN"), "Miền Bắc")
        self.assertEqual(normalize_region("Miền Nam"), "Miền Nam")
        self.assertEqual(normalize_region(""), "")
        self.assertEqual(normalize_region(None), "")

    def test_dynamic_column_detection_and_assignment(self):
        """
        Verify that fetch_active_agents automatically detects today's date column,
        personnel column named "Nhân sự", and region column named "Team TV".
        """
        from assigner import fetch_active_agents, tz_vietnam
        # Let's mock a TVV record with sheet style columns
        now_vn = datetime.now(tz_vietnam)
        today_col = now_vn.strftime("%d/%m")
        
        tvvs_records = [
            {
                "record_id": "rec_tvv_dynamic",
                "fields": {
                    "Nhân sự": [{"id": "user_dyn", "name": "Dynamic User"}],
                    "Team TV": "Hà Nội",
                    "Hình thức": "Chính thức",
                    today_col: True
                }
            }
        ]
        self.client.list_records.return_value = tvvs_records
        
        active = fetch_active_agents(self.client, "TVV")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["user_id"], "user_dyn")
        self.assertEqual(active[0]["name"], "Dynamic User")
        self.assertEqual(active[0]["region"], "Miền Bắc") # "Hà Nội" normalized

    def test_robust_dynamic_column_detection(self):
        """
        Verify dynamic column detection behaves correctly with complex date formats,
        various column names (Họ và tên, Chi nhánh, Loại), and extra spaces.
        """
        from assigner import fetch_active_agents, tz_vietnam
        now_vn = datetime.now(tz_vietnam)
        # Match e.g., "21/5/2026"
        today_col = f"{now_vn.day}/{now_vn.month}/{now_vn.year}"
        
        tvvs_records = [
            {
                "record_id": "rec_tvv_robust",
                "fields": {
                    " Họ và tên  ": [{"id": "user_robust", "name": "Robust User"}],
                    " Chi nhánh  ": "HCM",
                    " Loại ": "TVV",
                    today_col: True
                }
            }
        ]
        self.client.list_records.return_value = tvvs_records
        
        active = fetch_active_agents(self.client, "TVV")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["user_id"], "user_robust")
        self.assertEqual(active[0]["name"], "Robust User")
        self.assertEqual(active[0]["region"], "Miền Nam") # "HCM" normalized

if __name__ == "__main__":
    unittest.main()
