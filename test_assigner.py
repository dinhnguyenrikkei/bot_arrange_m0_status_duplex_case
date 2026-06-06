import unittest
from unittest.mock import MagicMock, patch
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
config.COOLDOWN_MINUTES_BETWEEN_CALLS = 15

from assigner import (
    check_tvv_availability,
    assign_m0_lead_to_tvv,
    assign_t0_leads_to_tts,
    build_assignment_update_fields,
    get_today_range,
    fetch_today_schedule,
    _is_field_empty,
    assign_m0_leads_batch,
    tz_vietnam
)
from lark_client import LarkClient

class TestLeadAssignment(unittest.TestCase):
    
    def setUp(self):
        # Create a mock Lark client
        self.client = MagicMock(spec=LarkClient)
        # Default: field type is Person (11) for backward compatibility
        self.client.get_field_type.return_value = 11
        
    def test_today_range(self):
        start, end = get_today_range()
        self.assertTrue(start < end)
        # Ensure it represents roughly 24 hours
        diff_hours = (end - start) / (1000 * 60 * 60)
        self.assertAlmostEqual(diff_hours, 24.0, delta=0.1)

    def test_check_tvv_availability(self):
        # TVV is busy if they have a callback within 15 minutes of the target callback time.
        target_time = 1716200000000 # 2026-05-20 approx.
        cooldown_ms = 15 * 60 * 1000
        
        # Test case 1: No previous assignments today -> Should be Free
        self.assertTrue(check_tvv_availability("user_1", target_time, []))
        
        # Test case 2: Previous assignment with callback at the exact same time -> Should be Busy
        assignments = [
            {"assigned_user_id": "user_1", "callback_time": target_time, "assigned_time": int(time.time() * 1000)}
        ]
        self.assertFalse(check_tvv_availability("user_1", target_time, assignments))
        
        # Test case 3: Previous assignment is far away (e.g. 20 minutes before) -> Should be Free
        assignments = [
            {"assigned_user_id": "user_1", "callback_time": target_time - (20 * 60 * 1000), "assigned_time": int(time.time() * 1000)}
        ]
        self.assertTrue(check_tvv_availability("user_1", target_time, assignments))
        
        # Test case 4: Previous assignment is close (e.g. 10 minutes after) -> Should be Busy
        assignments = [
            {"assigned_user_id": "user_1", "callback_time": target_time + (10 * 60 * 1000), "assigned_time": int(time.time() * 1000)}
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
        self.client.list_records.side_effect = lambda table_id, **kwargs: tvvs_records if table_id == config.TABLE_TVV_ID else []
        
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
        
        def mock_list_records(table_id, **kwargs):
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
        
        def mock_list_records(table_id, **kwargs):
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
        self.client.list_records.side_effect = lambda table_id, **kwargs: tvvs_records if table_id == config.TABLE_TVV_ID else []
        
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
        
        def mock_list_records(table_id, **kwargs):
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

    def test_build_assignment_update_fields_person_type(self):
        """When 'Tư vấn viên' is Person (type 11), both fields should be filled."""
        self.client.get_field_type.return_value = 11  # Person
        result = build_assignment_update_fields(self.client, "ou_abc", 1000)
        self.assertEqual(result[config.FIELD_TIKTOK_ASSIGNED_USER], [{"id": "ou_abc"}])
        self.assertEqual(result[config.FIELD_TIKTOK_RECIPIENT_USER], [{"id": "ou_abc"}])
        self.assertEqual(result[config.FIELD_TIKTOK_ASSIGNED_TIME], 1000)

    def test_build_assignment_update_fields_link_type_skipped(self):
        """When 'Tư vấn viên' is Link (type 18), it should be SKIPPED. Only 'Người nhận data' is filled."""
        self.client.get_field_type.return_value = 18  # Link
        result = build_assignment_update_fields(self.client, "ou_abc", 1000)
        # 'Tư vấn viên' should NOT be in update_fields
        self.assertNotIn(config.FIELD_TIKTOK_ASSIGNED_USER, result)
        # 'Người nhận data' should still be filled
        self.assertEqual(result[config.FIELD_TIKTOK_RECIPIENT_USER], [{"id": "ou_abc"}])
        self.assertEqual(result[config.FIELD_TIKTOK_ASSIGNED_TIME], 1000)

    def test_build_assignment_update_fields_none_type_fallback(self):
        """When field type detection fails (returns None), fall back to Person format."""
        self.client.get_field_type.return_value = None
        result = build_assignment_update_fields(self.client, "ou_abc", 1000)
        # Should fall back to Person format
        self.assertEqual(result[config.FIELD_TIKTOK_ASSIGNED_USER], [{"id": "ou_abc"}])
        self.assertEqual(result[config.FIELD_TIKTOK_RECIPIENT_USER], [{"id": "ou_abc"}])

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


class TestFetchTodaySchedule(unittest.TestCase):
    """Tests for the new fetch_today_schedule function (replaces fetch_today_assignments)."""

    def setUp(self):
        self.client = MagicMock(spec=LarkClient)

    def test_includes_records_with_callback_today(self):
        """Records with callback_time in today's range should be included."""
        start_ms, end_ms = get_today_range()
        records = [
            {
                "record_id": "rec1",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_1", "name": "User 1"}],
                    config.FIELD_TIKTOK_ASSIGNED_TIME: start_ms - 86400000,  # Assigned yesterday
                    config.FIELD_TIKTOK_CALLBACK_TIME: start_ms + 3600000   # Callback today
                }
            }
        ]
        self.client.list_records.return_value = records
        
        result = fetch_today_schedule(self.client)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["assigned_user_id"], "user_1")

    def test_includes_records_assigned_today_without_callback(self):
        """Records assigned today even without callback should be included."""
        start_ms, _ = get_today_range()
        records = [
            {
                "record_id": "rec2",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_2", "name": "User 2"}],
                    config.FIELD_TIKTOK_ASSIGNED_TIME: start_ms + 1000,
                    # No callback time
                }
            }
        ]
        self.client.list_records.return_value = records
        
        result = fetch_today_schedule(self.client)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["assigned_user_id"], "user_2")

    def test_skips_records_without_assigned_user(self):
        """Records without any assigned user should be skipped."""
        start_ms, _ = get_today_range()
        records = [
            {
                "record_id": "rec3",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_TIME: start_ms + 1000,
                    config.FIELD_TIKTOK_CALLBACK_TIME: start_ms + 3600000
                    # No assigned user
                }
            }
        ]
        self.client.list_records.return_value = records
        
        result = fetch_today_schedule(self.client)
        self.assertEqual(len(result), 0)

    def test_falls_back_to_recipient_user_for_user_id(self):
        """If TVV field is empty but Người nhận data is filled, use recipient user_id."""
        start_ms, _ = get_today_range()
        records = [
            {
                "record_id": "rec4",
                "fields": {
                    config.FIELD_TIKTOK_RECIPIENT_USER: [{"id": "user_r", "name": "Recipient"}],
                    config.FIELD_TIKTOK_ASSIGNED_TIME: start_ms + 1000,
                    config.FIELD_TIKTOK_CALLBACK_TIME: start_ms + 3600000
                    # TVV field (FIELD_TIKTOK_ASSIGNED_USER) is empty
                }
            }
        ]
        self.client.list_records.return_value = records
        
        result = fetch_today_schedule(self.client)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["assigned_user_id"], "user_r")

    def test_excludes_old_records_without_today_relevance(self):
        """Records assigned yesterday with callback yesterday should be excluded."""
        start_ms, _ = get_today_range()
        records = [
            {
                "record_id": "rec_old",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_old", "name": "Old User"}],
                    config.FIELD_TIKTOK_ASSIGNED_TIME: start_ms - 86400000,  # Yesterday
                    config.FIELD_TIKTOK_CALLBACK_TIME: start_ms - 43200000   # Yesterday
                }
            }
        ]
        self.client.list_records.return_value = records
        
        result = fetch_today_schedule(self.client)
        self.assertEqual(len(result), 0)


class TestIsFieldEmpty(unittest.TestCase):
    """Tests for the _is_field_empty helper."""

    def test_none_is_empty(self):
        self.assertTrue(_is_field_empty(None))

    def test_empty_list_is_empty(self):
        self.assertTrue(_is_field_empty([]))

    def test_empty_string_is_empty(self):
        self.assertTrue(_is_field_empty(""))
        self.assertTrue(_is_field_empty("   "))

    def test_false_is_empty(self):
        self.assertTrue(_is_field_empty(False))

    def test_filled_list_is_not_empty(self):
        self.assertFalse(_is_field_empty([{"id": "user_1"}]))

    def test_filled_string_is_not_empty(self):
        self.assertFalse(_is_field_empty("some value"))

    def test_filled_dict_is_not_empty(self):
        self.assertFalse(_is_field_empty({"text": "Name"}))

    def test_empty_link_field_dict_is_empty(self):
        """Link field (type 18) returns {"link_record_ids": []} when empty."""
        self.assertTrue(_is_field_empty({"link_record_ids": []}))
        self.assertTrue(_is_field_empty({"link_record_ids": [], "table_id": "tblXXX"}))

    def test_filled_link_field_dict_is_not_empty(self):
        """Link field with actual records should not be empty."""
        self.assertFalse(_is_field_empty({"link_record_ids": ["recABC"]}))

    def test_empty_text_dict_is_empty(self):
        self.assertTrue(_is_field_empty({"text": ""}))
        self.assertTrue(_is_field_empty({"text": "  "}))

    # ── DuplexLink (type 21) tests ──

    def test_empty_duplex_link_dict_is_empty(self):
        """DuplexLink (type 21) returns {"record_ids": []} when empty."""
        self.assertTrue(_is_field_empty({"record_ids": []}))
        self.assertTrue(_is_field_empty({"record_ids": [], "table_id": "tblXXX"}))

    def test_filled_duplex_link_dict_is_not_empty(self):
        """DuplexLink with actual records should not be empty."""
        self.assertFalse(_is_field_empty({"record_ids": ["recABC"]}))

    def test_empty_duplex_link_list_of_dicts_is_empty(self):
        """DuplexLink can also return [{"record_ids": [], "table_id": "tblXXX"}]."""
        self.assertTrue(_is_field_empty([{"record_ids": []}]))
        self.assertTrue(_is_field_empty([{"record_ids": [], "table_id": "tblXXX"}]))

    def test_filled_duplex_link_list_of_dicts_is_not_empty(self):
        """DuplexLink list with actual records should not be empty."""
        self.assertFalse(_is_field_empty([{"record_ids": ["recABC"], "table_id": "tblXXX"}]))

    def test_person_field_list_is_not_empty(self):
        """Person field like [{"id": "ou_xxx"}] must NOT be treated as empty."""
        self.assertFalse(_is_field_empty([{"id": "ou_xxx"}]))
        self.assertFalse(_is_field_empty([{"id": "ou_xxx", "name": "Someone"}]))


class TestBatchAssignmentModes(unittest.TestCase):
    """Tests for the 3 modes of assign_m0_leads_batch."""

    def setUp(self):
        self.client = MagicMock(spec=LarkClient)
        self.client.get_field_type.return_value = 11  # Person type by default

    def test_mirror_mode_fills_recipient_via_roundrobin(self):
        """Mirror mode: TVV filled but Người nhận data empty → fill recipient via round-robin by region."""
        from datetime import datetime
        now_vn = datetime.now(tz_vietnam)
        today_col = now_vn.strftime("%d/%m")
        
        leads = [
            {
                "record_id": "lead_mirror",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_tvv", "name": "TVV Name"}],
                    config.FIELD_TIKTOK_RECIPIENT_USER: None,  # Empty
                    config.FIELD_TIKTOK_REGION: "Miền Bắc",
                }
            }
        ]
        
        # Mock dispatch table with active agent (with Người nhận data column)
        tvv_dispatch_records = [
            {
                "record_id": "dispatch_1",
                "fields": {
                    config.FIELD_TVV_USER: [{"id": "user_agent", "name": "Agent Name"}],
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    "Người nhận data": [{"id": "user_recipient", "name": "Recipient Person"}],
                    today_col: True,
                }
            }
        ]
        
        def mock_list_records(table_id, **kwargs):
            if table_id == config.TABLE_TVV_ID:
                return tvv_dispatch_records
            elif table_id == config.TABLE_TIKTOK_ID:
                return []  # No existing assignments
            return []
        
        self.client.list_records.side_effect = mock_list_records
        
        results = assign_m0_leads_batch(self.client, leads)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "lead_mirror")
        self.client.batch_update_records.assert_called_once()
        
        # Verify that the recipient_user_id from dispatch table was used
        call_args = self.client.batch_update_records.call_args[0]
        records_updated = call_args[1]
        update_fields = records_updated[0]["fields"]
        self.assertEqual(update_fields[config.FIELD_TIKTOK_RECIPIENT_USER], [{"id": "user_recipient"}])

    def test_mirror_mode_selects_by_region(self):
        """Mirror mode: With agents in different regions, round-robin should prefer same region."""
        from datetime import datetime
        now_vn = datetime.now(tz_vietnam)
        today_col = now_vn.strftime("%d/%m")
        
        leads = [
            {
                "record_id": "lead_north",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_tvv", "name": "TVV"}],
                    config.FIELD_TIKTOK_RECIPIENT_USER: None,
                    config.FIELD_TIKTOK_REGION: "Miền Bắc",
                }
            }
        ]
        
        tvv_records = [
            {
                "record_id": "dispatch_north",
                "fields": {
                    config.FIELD_TVV_USER: [{"id": "user_north", "name": "North Agent"}],
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    today_col: True,
                }
            },
            {
                "record_id": "dispatch_south",
                "fields": {
                    config.FIELD_TVV_USER: [{"id": "user_south", "name": "South Agent"}],
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Nam",
                    today_col: True,
                }
            }
        ]
        
        def mock_list_records(table_id, **kwargs):
            if table_id == config.TABLE_TVV_ID:
                return tvv_records
            elif table_id == config.TABLE_TIKTOK_ID:
                return []
            return []
        
        self.client.list_records.side_effect = mock_list_records
        
        results = assign_m0_leads_batch(self.client, leads)
        self.assertEqual(len(results), 1)
        # Should pick the North agent (same region as lead)
        self.assertEqual(results[0][1]["user_id"], "user_north")

    def test_reverse_mirror_mode_fills_tvv_person(self):
        """Reverse-mirror mode: Người nhận data filled, TVV empty, Person field → fill TVV."""
        leads = [
            {
                "record_id": "lead_reverse",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: None,  # Empty
                    config.FIELD_TIKTOK_RECIPIENT_USER: [{"id": "user_recip", "name": "Recipient Name"}],
                    config.FIELD_TIKTOK_REGION: "Miền Bắc",
                }
            }
        ]
        
        self.client.list_records.return_value = []
        
        results = assign_m0_leads_batch(self.client, leads)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "lead_reverse")
        # Check that batch_update was called with TVV person field filled
        call_args = self.client.batch_update_records.call_args[0]
        records_updated = call_args[1]
        self.assertEqual(len(records_updated), 1)
        update_fields = records_updated[0]["fields"]
        self.assertEqual(update_fields[config.FIELD_TIKTOK_ASSIGNED_USER], [{"id": "user_recip"}])

    def test_roundrobin_mode_both_empty(self):
        """Round-robin mode: both fields empty → assign via round-robin."""
        leads = [
            {
                "record_id": "lead_rr",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: None,
                    config.FIELD_TIKTOK_RECIPIENT_USER: None,
                    config.FIELD_TIKTOK_REGION: "Miền Bắc",
                    config.FIELD_TIKTOK_CALLBACK_TIME: None,
                }
            }
        ]
        
        # Mock TVV dispatch records for active agents
        start_ms, _ = get_today_range()
        now_vn = datetime.now(tz_vietnam)
        today_col = now_vn.strftime("%d/%m")
        
        tvv_records = [
            {
                "record_id": "rec_tvv_rr",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    config.FIELD_TVV_USER: [{"id": "user_rr", "name": "Round Robin TVV"}],
                    today_col: True,
                }
            }
        ]
        
        def mock_list_records(table_id, **kwargs):
            if table_id == config.TABLE_TVV_ID:
                return tvv_records
            elif table_id == config.TABLE_TIKTOK_ID:
                return []  # No existing assignments
            return []

        self.client.list_records.side_effect = mock_list_records
        
        results = assign_m0_leads_batch(self.client, leads)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "lead_rr")
        self.client.batch_update_records.assert_called_once()

    def test_roundrobin_uses_recipient_user_id_from_dispatch(self):
        """Round-robin mode: should use recipient_user_id from dispatch table's 'Người nhận data' column."""
        now_vn = datetime.now(tz_vietnam)
        today_col = now_vn.strftime("%d/%m")
        
        leads = [
            {
                "record_id": "lead_rr_recip",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: None,
                    config.FIELD_TIKTOK_RECIPIENT_USER: None,
                    config.FIELD_TIKTOK_REGION: "Miền Bắc",
                    config.FIELD_TIKTOK_CALLBACK_TIME: None,
                }
            }
        ]
        
        # Dispatch table has separate Người nhận data column with different user_id
        tvv_records = [
            {
                "record_id": "rec_tvv_dispatch",
                "fields": {
                    config.FIELD_TVV_ROLE: "TVV",
                    config.FIELD_TVV_ACTIVE: True,
                    config.FIELD_TVV_REGION: "Miền Bắc",
                    config.FIELD_TVV_USER: [{"id": "user_personnel", "name": "Personnel Name"}],
                    "Người nhận data": [{"id": "user_nnd", "name": "NND Person"}],
                    today_col: True,
                }
            }
        ]
        
        def mock_list_records(table_id, **kwargs):
            if table_id == config.TABLE_TVV_ID:
                return tvv_records
            elif table_id == config.TABLE_TIKTOK_ID:
                return []
            return []
        
        self.client.list_records.side_effect = mock_list_records
        
        results = assign_m0_leads_batch(self.client, leads)
        self.assertEqual(len(results), 1)
        
        # Verify Người nhận data uses the dispatch table's Người nhận data user_id
        call_args = self.client.batch_update_records.call_args[0]
        records_updated = call_args[1]
        update_fields = records_updated[0]["fields"]
        self.assertEqual(update_fields[config.FIELD_TIKTOK_RECIPIENT_USER], [{"id": "user_nnd"}])

    def test_skips_fully_assigned_leads(self):
        """Leads with both TVV and Người nhận data filled should be skipped."""
        leads = [
            {
                "record_id": "lead_full",
                "fields": {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": "user_a", "name": "A"}],
                    config.FIELD_TIKTOK_RECIPIENT_USER: [{"id": "user_a", "name": "A"}],
                    config.FIELD_TIKTOK_REGION: "Miền Bắc",
                }
            }
        ]
        
        results = assign_m0_leads_batch(self.client, leads)
        self.assertEqual(len(results), 0)
        self.client.batch_update_records.assert_not_called()


if __name__ == "__main__":
    unittest.main()
