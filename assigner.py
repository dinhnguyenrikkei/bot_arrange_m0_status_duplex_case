import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import config
from lark_client import LarkClient

logger = logging.getLogger(__name__)

# Vietnam Timezone (GMT+7)
tz_vietnam = timezone(timedelta(hours=7))

def get_today_range() -> Tuple[int, int]:
    """
    Get the millisecond timestamps for the start and end of today in Vietnam timezone.
    """
    now_vn = datetime.now(tz_vietnam)
    today_start = datetime(now_vn.year, now_vn.month, now_vn.day, 0, 0, 0, tzinfo=tz_vietnam)
    today_end = today_start + timedelta(days=1) - timedelta(seconds=1)
    return int(today_start.timestamp() * 1000), int(today_end.timestamp() * 1000)

def parse_personnel_field(field_value: Any) -> Optional[Tuple[str, str]]:
    """
    Parse Lark personnel field to extract user_id and name.
    Lark personnel field structure is typically a list of dicts:
    [{"id": "ou_...", "name": "..."}]
    """
    if isinstance(field_value, list) and len(field_value) > 0:
        person = field_value[0]
        if isinstance(person, dict):
            return person.get("id"), person.get("name")
    return None

def normalize_region(region_value: str) -> str:
    """
    Normalize region values to a standard key.
    - "Hà Nội", "HN", "Miền Bắc", etc. -> "Miền Bắc"
    - "HCM", "Hồ Chí Minh", "Sài Gòn", "Miền Nam", etc. -> "Miền Nam"
    - "Đà Nẵng", "Miền Trung", etc. -> "Miền Trung"
    """
    if not region_value:
        return ""
    val_norm = str(region_value).lower().strip()
    if "hà nội" in val_norm or "ha noi" in val_norm or "hn" == val_norm or "bắc" in val_norm:
        return "Miền Bắc"
    if "hcm" in val_norm or "ho chi minh" in val_norm or "hồ chí minh" in val_norm or "sài gòn" in val_norm or "sai gon" in val_norm or "nam" in val_norm:
        return "Miền Nam"
    if "đà nẵng" in val_norm or "da nang" in val_norm or "trung" in val_norm:
        return "Miền Trung"
    return region_value

def is_eligible_for_distribution(fields: Dict[str, Any]) -> bool:
    """
    Check if the lead is eligible for distribution based on source and channel requirements:
    - Nguồn Data must be "Online - Digital MKT"
    - Kênh đăng ký must be "Tiktok"
    """
    def extract_text(val):
        if not val:
            return ""
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, list):
            if len(val) > 0 and isinstance(val[0], dict) and "text" in val[0]:
                return "".join([v.get("text", "") for v in val]).strip()
            return ", ".join([str(v) for v in val]).strip()
        if isinstance(val, dict):
            return val.get("text", "").strip()
        return str(val).strip()

    source = extract_text(fields.get("Nguồn Data"))
    channel = extract_text(fields.get("Kênh đăng ký"))
    
    return source == "Online - Digital MKT" and channel == "Tiktok"

def parse_weight_from_note(note_value: Any) -> float:
    """
    Parse a weight/percentage from the 'Ghi chú' (Notes) column.
    Examples:
        "70%"  -> 0.7
        "50%"  -> 0.5
        "100%" -> 1.0
        ""     -> 1.0 (default)
        None   -> 1.0 (default)
    Returns a float between 0.01 and 1.0.
    """
    if not note_value:
        return 1.0
    text = str(note_value).strip()
    # Try to extract a number before '%'
    import re
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if match:
        pct = float(match.group(1))
        weight = pct / 100.0
        # Clamp between 0.01 and 1.0
        return max(0.01, min(1.0, weight))
    # Try plain number (e.g. "0.7" or "70")
    try:
        val = float(text)
        if val > 1.0:
            val = val / 100.0
        return max(0.01, min(1.0, val))
    except (ValueError, TypeError):
        return 1.0

def detect_tvv_columns(records: List[Dict[str, Any]], date_candidates: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Dynamically detect the column/field names for:
    - Active Today Checkbox
    - Personnel (Nhân sự)
    - Region (Team TV / Khu vực)
    - Role (Vai trò / Hình thức - optional)
    Returns: (active_field, personnel_field, region_field, role_field)
    """
    all_keys = set()
    for rec in records:
        all_keys.update(rec.get("fields", {}).keys())
        
    active_field = None
    personnel_field = None
    region_field = None
    role_field = None
    
    # 1. Detect Active Today Checkbox column
    for k in all_keys:
        k_clean = k.strip()
        if k_clean in date_candidates:
            active_field = k
            break
            
    # 2. Detect Personnel (Nhân sự) column
    for k in all_keys:
        k_low = k.lower().strip()
        if k_low in ["nhân sự", "nhân viên", "tư vấn viên", "tvv", "họ tên", "tên", "nhan su", "nhan vien", "tu van vien", "ho ten", "ten"]:
            personnel_field = k
            break
    if not personnel_field:
        for k in all_keys:
            k_low = k.lower().strip()
            if any(kw in k_low for kw in ["nhân sự", "nhân viên", "tư vấn viên", "tvv", "họ tên", "họ và tên", "tên", "nhan su", "nhan vien", "tu van vien", "ho ten", "ten"]):
                personnel_field = k
                break
    if not personnel_field:
        for rec in records:
            for k, v in rec.get("fields", {}).items():
                if parse_personnel_field(v):
                    personnel_field = k
                    break
            if personnel_field:
                break
                
    # 3. Detect Region (Team TV / Khu vực) column
    for k in all_keys:
        k_low = k.lower().strip()
        if k_low in ["team tv", "team", "khu vực", "chi nhánh", "địa điểm", "vùng", "khu vuc", "chi nhanh", "dia diem"]:
            region_field = k
            break
    if not region_field:
        for k in all_keys:
            k_low = k.lower().strip()
            if any(kw in k_low for kw in ["team", "khu vực", "khu vuc", "chi nhánh", "chi nhanh", "vùng", "vung", "cơ sở", "co so"]):
                region_field = k
                break
    if not region_field:
        for rec in records:
            for k, v in rec.get("fields", {}).items():
                if isinstance(v, str):
                    norm = normalize_region(v)
                    if norm in ["Miền Bắc", "Miền Nam", "Miền Trung"]:
                        region_field = k
                        break
            if region_field:
                break
                
    # 4. Detect Role (Vai trò / Hình thức - optional) column
    for k in all_keys:
        k_low = k.lower().strip()
        if k_low in ["vai trò", "role", "hình thức", "loại", "vai tro", "hinh thuc", "loai"]:
            role_field = k
            break
    if not role_field:
        for k in all_keys:
            k_low = k.lower().strip()
            if any(kw in k_low for kw in ["vai trò", "role", "hình thức", "loại", "vai tro", "hinh thuc", "loai"]):
                role_field = k
                break
            
    return active_field, personnel_field, region_field, role_field

def fetch_active_agents(client: LarkClient, role: str) -> List[Dict[str, Any]]:
    """
    Fetch active agents (TTS or TVV) from Bitable TVV Table.
    """
    try:
        records = client.list_records(config.TABLE_TVV_ID)
        active_agents = []
        
        # Initialize user_map as None to load lazily only if fallback is needed
        user_map = None
        
        # Determine today's date in GMT+7 and candidate formats
        now_vn = datetime.now(tz_vietnam)
        day = now_vn.day
        month = now_vn.month
        year = now_vn.year
        year_short = str(year)[-2:]
        
        date_candidates = [
            f"{day:02d}/{month:02d}",  # "21/05"
            f"{day}/{month}",          # "21/5"
            f"{day:02d}-{month:02d}",  # "21-05"
            f"{day}-{month}",          # "21-5"
            f"{day:02d}/{month:02d}/{year}",  # "21/05/2026"
            f"{day}/{month}/{year}",          # "21/5/2026"
            f"{day:02d}/{month:02d}/{year_short}",  # "21/05/26"
            f"{day}/{month}/{year_short}",          # "21/5/26"
            f"{year}-{month:02d}-{day:02d}",  # "2026-05-21"
            f"{day:02d}.{month:02d}",  # "21.05"
            f"{day}.{month}",          # "21.5"
            str(day),                  # "8"
            f"{day:02d}",              # "08"
        ]
        
        # Dynamically detect columns
        active_col, personnel_col, region_col, role_col = detect_tvv_columns(
            records, date_candidates
        )
        
        # Determine all keys in the sheet
        all_keys = set()
        for rec in records:
            all_keys.update(rec.get("fields", {}).keys())
            
        # Priority: Config value first (if present in fields), then auto-detected value
        active_col = config.FIELD_TVV_ACTIVE if config.FIELD_TVV_ACTIVE in all_keys else (active_col or config.FIELD_TVV_ACTIVE)
        personnel_col = config.FIELD_TVV_USER if config.FIELD_TVV_USER in all_keys else (personnel_col or config.FIELD_TVV_USER)
        region_col = config.FIELD_TVV_REGION if config.FIELD_TVV_REGION in all_keys else (region_col or config.FIELD_TVV_REGION)
        role_col = config.FIELD_TVV_ROLE if config.FIELD_TVV_ROLE in all_keys else (role_col or config.FIELD_TVV_ROLE)
        
        # Detect "Người nhận data" column in dispatch table
        recipient_col = None
        for k in all_keys:
            k_low = k.lower().strip()
            if "người nhận" in k_low or "nguoi nhan" in k_low:
                recipient_col = k
                break
        
        # Detect "Tư vấn viên" Link column in dispatch table
        tvv_link_col = None
        for k in all_keys:
            k_low = k.lower().strip()
            if "tư vấn" in k_low or "tu van" in k_low:
                tvv_link_col = k
                break
        
        # Detect "Ghi chú" (Notes) column for weight/percentage
        note_col = None
        for k in all_keys:
            k_low = k.lower().strip()
            if k_low in ["ghi chú", "ghi chu", "note", "notes"]:
                note_col = k
                break
        if not note_col:
            for k in all_keys:
                k_low = k.lower().strip()
                if any(kw in k_low for kw in ["ghi chú", "ghi chu", "note", "tỷ lệ", "ty le", "%"]):
                    note_col = k
                    break
        
        logger.info(f"Final columns selected: active={active_col}, personnel={personnel_col}, region={region_col}, role={role_col}, recipient={recipient_col}, tvv_link={tvv_link_col}, note={note_col}")
        
        for rec in records:
            fields = rec.get("fields", {})
            
            # Check role if column present and has value
            if role_col in fields:
                agent_role = fields.get(role_col)
                if agent_role and agent_role != role:
                    agent_role_str = str(agent_role).lower().strip()
                    requested_role_str = str(role).lower().strip()
                    if agent_role_str in ["tts", "tvv"] and agent_role_str != requested_role_str:
                        continue
                
            # Check if active today
            is_active = fields.get(active_col, False)
            if not is_active:
                continue
                
            # Parse Personnel field
            person_val = fields.get(personnel_col)
            person_info = parse_personnel_field(person_val)
            if not person_info and isinstance(person_val, str) and person_val.strip():
                # Fallback to name-to-id mapping, fetch user_map lazily if not already loaded
                if user_map is None:
                    try:
                        user_map = client.fetch_all_users()
                        logger.info(f"Fetched {len(user_map)} contact users for fallback name mapping (lazy loaded).")
                    except Exception as e:
                        logger.warning(f"Could not fetch contact users for fallback name mapping: {e}")
                        user_map = {}
                norm_name = person_val.strip()
                user_id = user_map.get(norm_name.lower())
                if user_id:
                    person_info = (user_id, norm_name)
                    logger.info(f"Resolved personnel '{norm_name}' to User ID '{user_id}' via contact mapping.")
                
            if not person_info:
                logger.warning(f"TVV record {rec.get('record_id')} has no valid personnel account configured in column '{personnel_col}' (value: '{person_val}').")
                continue
            
            user_id_check, name_check = person_info
            if not user_id_check:
                logger.warning(f"TVV record {rec.get('record_id')} has personnel field but user_id is None. Column '{personnel_col}' may be DuplexLink instead of Person. Skipping.")
                continue
                
            user_id, name = person_info
            raw_region = fields.get(region_col, "")
            region = normalize_region(raw_region)
            
            # Extract recipient user_id from "Người nhận data" column in dispatch table
            recipient_user_id = None
            if recipient_col:
                recipient_val = fields.get(recipient_col)
                recipient_info = parse_personnel_field(recipient_val)
                if recipient_info:
                    recipient_user_id = recipient_info[0]
            
            # Extract tvv_link_record_id from "Tư vấn viên" Link column in dispatch table
            tvv_link_record_id = None
            if tvv_link_col:
                tvv_link_val = fields.get(tvv_link_col)
                if isinstance(tvv_link_val, list) and len(tvv_link_val) > 0:
                    first = tvv_link_val[0]
                    if isinstance(first, dict):
                        rids = first.get("record_ids", [])
                        if rids:
                            tvv_link_record_id = rids[0]
                elif isinstance(tvv_link_val, dict):
                    rids = tvv_link_val.get("link_record_ids", []) or tvv_link_val.get("record_ids", [])
                    if rids:
                        tvv_link_record_id = rids[0]
            
            # Extract weight from "Ghi chú" column
            weight = 1.0
            if note_col:
                note_val = fields.get(note_col)
                weight = parse_weight_from_note(note_val)
            
            active_agents.append({
                "record_id": rec.get("record_id"),
                "user_id": user_id,
                "name": name,
                "region": region,
                "recipient_user_id": recipient_user_id or user_id,
                "tvv_link_record_id": tvv_link_record_id,
                "weight": weight,
            })
            
        logger.info(f"Found {len(active_agents)} active agents for role '{role}' today.")
        return active_agents
    except Exception as e:
        logger.error(f"Error fetching active agents: {e}")
        raise

def fetch_today_schedule(client: LarkClient) -> List[Dict[str, Any]]:
    """
    Fetch all TikTok leads that have a callback scheduled for today
    OR were assigned today, regardless of when the lead was created.
    This ensures schedule conflict detection works across days
    (e.g. bot was off yesterday, leads from yesterday still count).
    """
    try:
        start_ms, end_ms = get_today_range()
        records = client.list_records(config.TABLE_TIKTOK_ID)
        
        today_schedule = []
        for rec in records:
            fields = rec.get("fields", {})
            callback_time = fields.get(config.FIELD_TIKTOK_CALLBACK_TIME)
            assigned_time = fields.get(config.FIELD_TIKTOK_ASSIGNED_TIME)
            
            # Include records that:
            # 1. Have a callback scheduled for today, OR
            # 2. Were assigned today (even without callback)
            has_today_callback = callback_time and start_ms <= callback_time <= end_ms
            assigned_today = assigned_time and start_ms <= assigned_time <= end_ms
            
            if has_today_callback or assigned_today:
                person_info = parse_personnel_field(fields.get(config.FIELD_TIKTOK_ASSIGNED_USER))
                assigned_user_id = person_info[0] if person_info else None
                
                # Also try to get user_id from Người nhận data if TVV field is a link
                if not assigned_user_id:
                    recipient_info = parse_personnel_field(fields.get(config.FIELD_TIKTOK_RECIPIENT_USER))
                    assigned_user_id = recipient_info[0] if recipient_info else None
                
                # Skip records without any assigned user
                if not assigned_user_id:
                    continue
                
                today_schedule.append({
                    "record_id": rec.get("record_id"),
                    "assigned_user_id": assigned_user_id,
                    "assigned_time": assigned_time,
                    "callback_time": callback_time
                })
                
        logger.info(f"Found {len(today_schedule)} scheduled calls for today.")
        return today_schedule
    except Exception as e:
        logger.error(f"Error fetching today schedule: {e}")
        raise

def check_tvv_availability(tvv_user_id: str, target_callback_ms: Optional[int], today_assignments: List[Dict[str, Any]]) -> bool:
    """
    Check if a TVV is free during the target callback time.
    TVV is busy if they have an existing callback within 30 minutes of the target callback.
    If target_callback_ms is None, treat it as the current time.
    """
    if target_callback_ms is None:
        target_callback_ms = int(time.time() * 1000)
        
    cooldown_ms = config.COOLDOWN_MINUTES_BETWEEN_CALLS * 60 * 1000
    
    for ass in today_assignments:
        if ass["assigned_user_id"] == tvv_user_id:
            existing_cb = ass.get("callback_time")
            if existing_cb is not None:
                if abs(existing_cb - target_callback_ms) < cooldown_ms:
                    return False # Busy!
                    
    return True # Free!

def find_next_free_slot(tvv_user_id: str, start_time_ms: int, today_assignments: List[Dict[str, Any]]) -> int:
    """
    Find the next available callback time (in ms) for a TVV starting from start_time_ms.
    Shifts the time by config.COOLDOWN_MINUTES_BETWEEN_CALLS in each step until a slot is free.
    """
    candidate_ms = start_time_ms
    cooldown_ms = config.COOLDOWN_MINUTES_BETWEEN_CALLS * 60 * 1000
    
    while not check_tvv_availability(tvv_user_id, candidate_ms, today_assignments):
        candidate_ms += cooldown_ms
        
    return candidate_ms

def assign_t0_leads_to_tts(client: LarkClient) -> int:
    """
    [DISABLED] Distribute T0 leads in TikTok table to active TTS (daily at 8 AM).
    This function has been deactivated.
    """
    logger.info("T0 distribution to TTS is disabled.")
    return 0

def select_best_tvv_for_lead(
    lead_region: str,
    target_callback_time: int,
    active_tvvs: List[Dict[str, Any]],
    today_assignments: List[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    Select the best available TVV for a lead using regional preference, cooldown-based availability,
    and round-robin workload distribution. Shifting callback time if busy.
    Returns: (selected_tvv_dict, final_callback_time)
    """
    # Calculate metrics for each active TVV
    for tvv in active_tvvs:
        # Use recipient_user_id for matching (this is what gets written to TikTok records)
        match_id = tvv.get("recipient_user_id", tvv["user_id"])
        # Count assignments today
        tvv_assignments = [a for a in today_assignments if a["assigned_user_id"] == match_id]
        tvv["count_today"] = len(tvv_assignments)
        
        # Last assignment time today
        valid_times = [a["assigned_time"] for a in tvv_assignments if a.get("assigned_time") is not None]
        tvv["last_assigned_time"] = max(valid_times) if valid_times else 0
        
        # Availability based on schedule
        tvv["is_free"] = check_tvv_availability(match_id, target_callback_time, today_assignments)

    selected_tvv = None
    
    # Split candidates into primary region and other region
    primary_tvvs = [t for t in active_tvvs if t["region"] == lead_region]
    other_tvvs = [t for t in active_tvvs if t["region"] != lead_region]
    
    # Tier 1: Try same region TVVs who are free (based on cooldown)
    tier1_candidates = [t for t in primary_tvvs if t["is_free"]]
    
    if tier1_candidates:
        # Sort for Weighted Round-Robin: lower load ratio first, then oldest assignment time
        # load = count_today / weight → people with lower weight "fill up" faster
        tier1_candidates.sort(key=lambda x: (x["count_today"] / x.get("weight", 1.0), x["last_assigned_time"]))
        selected_tvv = tier1_candidates[0]
        logger.info(f"Selected TVV {selected_tvv['name']} from same region ({lead_region}) who is free.")
    else:
        # Tier 2: Try other region TVVs who are free
        logger.info(f"No free TVV in same region ({lead_region}). Attempting overflow to other region.")
        tier2_candidates = [t for t in other_tvvs if t["is_free"]]
        
        if tier2_candidates:
            tier2_candidates.sort(key=lambda x: (x["count_today"] / x.get("weight", 1.0), x["last_assigned_time"]))
            selected_tvv = tier2_candidates[0]
            logger.info(f"Selected TVV {selected_tvv['name']} from other region who is free.")
        else:
            # Tier 3 (Fallback): Everyone is busy. Pick from same region if possible, otherwise any active TVV
            logger.warning("Everyone is busy! Picking any active TVV to avoid leaving lead unassigned.")
            if primary_tvvs:
                primary_tvvs.sort(key=lambda x: (x["count_today"] / x.get("weight", 1.0), x["last_assigned_time"]))
                selected_tvv = primary_tvvs[0]
                logger.info(f"Selected TVV {selected_tvv['name']} from same region as fallback (busy).")
            else:
                other_tvvs.sort(key=lambda x: (x["count_today"] / x.get("weight", 1.0), x["last_assigned_time"]))
                selected_tvv = other_tvvs[0]
                logger.info(f"Selected TVV {selected_tvv['name']} from other region as fallback (busy).")
                
    if selected_tvv:
        # We always keep the original target callback time and do NOT shift it!
        return selected_tvv, target_callback_time
        
    return None, target_callback_time

def build_assignment_update_fields(
    client: LarkClient,
    tvv_user_id: str,
    current_time_ms: int,
    recipient_user_id: str = None,
) -> Dict[str, Any]:
    """
    Build the update fields dict, auto-detecting field types.
    - Person/User fields (type 11): filled with [{"id": tvv_user_id}]
    - Link fields (type 18): skipped (user fills manually or via Lark automation)
    - Unknown/error: falls back to Person format for safety
    
    recipient_user_id: If provided, used for 'Người nhận data' instead of tvv_user_id.
    """
    if recipient_user_id is None:
        recipient_user_id = tvv_user_id
    update_fields = {
        config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
        config.FIELD_TIKTOK_RECIPIENT_USER: [{"id": recipient_user_id}],
    }

    # Auto-detect field type for "Tư vấn viên" column
    field_type = client.get_field_type(
        config.TABLE_TIKTOK_ID, config.FIELD_TIKTOK_ASSIGNED_USER
    )

    if field_type == 11:  # Person/User → fill normally
        update_fields[config.FIELD_TIKTOK_ASSIGNED_USER] = [{"id": tvv_user_id}]
    elif field_type == 18:  # Link (One-way or Two-way) → skip
        logger.info(
            f"Field '{config.FIELD_TIKTOK_ASSIGNED_USER}' is a Link field (type 18). "
            f"Skipping auto-fill; only filling '{config.FIELD_TIKTOK_RECIPIENT_USER}'."
        )
    elif field_type is None:
        # Could not detect field type → fall back to Person format for safety
        logger.warning(
            f"Could not detect field type for '{config.FIELD_TIKTOK_ASSIGNED_USER}'. "
            f"Falling back to Person format."
        )
        update_fields[config.FIELD_TIKTOK_ASSIGNED_USER] = [{"id": tvv_user_id}]
    else:
        logger.info(
            f"Field '{config.FIELD_TIKTOK_ASSIGNED_USER}' has unsupported type {field_type}. "
            f"Skipping auto-fill."
        )

    return update_fields


def extract_tvv_name_from_field(field_value: Any) -> Optional[str]:
    """
    Extract the TVV display name from the 'Tư vấn viên' field.
    Handles multiple field formats:
    - Link field (type 18): may return {"text": "Name"}, [{"text": "Name"}],
      or a text-based representation
    - Person field (type 11): returns [{"id": "...", "name": "Name"}]
    - Plain text string
    Returns the extracted name, or None if empty.
    """
    if not field_value:
        return None

    # Case 1: List of dicts (Person field or Link field with text_arr)
    if isinstance(field_value, list) and len(field_value) > 0:
        first = field_value[0]
        if isinstance(first, dict):
            # Person field: {"id": "...", "name": "Name"}
            name = first.get("name") or first.get("text")
            if name:
                return name.strip()
        elif isinstance(first, str):
            # Sometimes link fields return a list of strings
            return first.strip()

    # Case 2: Dict with "text" key
    if isinstance(field_value, dict):
        text = field_value.get("text") or field_value.get("name")
        if text:
            return text.strip()
        # Link field might have "link_record_ids" and "text_arr"
        text_arr = field_value.get("text_arr")
        if isinstance(text_arr, list) and len(text_arr) > 0:
            return str(text_arr[0]).strip()

    # Case 3: Plain string
    if isinstance(field_value, str) and field_value.strip():
        return field_value.strip()

    return None


def build_tvv_name_to_userid_map(client: LarkClient) -> Dict[str, str]:
    """
    Build a mapping of TVV name (lowercase) -> user_id from the dispatch table (TVV table).
    This is used to look up the user_id for a TVV when 'Tư vấn viên' (Link field)
    is already filled and we just need to fill 'Người nhận data' (Person field).

    Falls back to contact user list if dispatch table personnel are text-only.
    """
    name_to_userid = {}

    try:
        records = client.list_records(config.TABLE_TVV_ID)

        # Determine the personnel column name
        now_vn = datetime.now(tz_vietnam)
        day = now_vn.day
        month = now_vn.month
        year = now_vn.year
        year_short = str(year)[-2:]
        date_candidates = [
            f"{day:02d}/{month:02d}", f"{day}/{month}",
            f"{day:02d}-{month:02d}", f"{day}-{month}",
            f"{day:02d}/{month:02d}/{year}", f"{day}/{month}/{year}",
            f"{day:02d}/{month:02d}/{year_short}", f"{day}/{month}/{year_short}",
            f"{year}-{month:02d}-{day:02d}",
            f"{day:02d}.{month:02d}", f"{day}.{month}",
        ]
        _, personnel_col, _, _ = detect_tvv_columns(records, date_candidates)

        all_keys = set()
        for rec in records:
            all_keys.update(rec.get("fields", {}).keys())
        personnel_col = config.FIELD_TVV_USER if config.FIELD_TVV_USER in all_keys else (personnel_col or config.FIELD_TVV_USER)

        # Also check if there's a "Người nhận data" column in the dispatch table
        recipient_col = None
        for k in all_keys:
            k_low = k.lower().strip()
            if "người nhận" in k_low or "nguoi nhan" in k_low or k_low == "người nhận data":
                recipient_col = k
                break

        user_map = None  # Lazy loaded contact mapping

        for rec in records:
            fields = rec.get("fields", {})

            # Get name from personnel column
            person_val = fields.get(personnel_col)
            person_info = parse_personnel_field(person_val)

            name = None
            user_id = None

            if person_info:
                user_id, name = person_info
            elif isinstance(person_val, str) and person_val.strip():
                name = person_val.strip()

            if not name:
                continue

            # If we have user_id from Person field, use it
            if user_id:
                name_to_userid[name.strip().lower()] = user_id
                continue

            # Try "Người nhận data" column in dispatch table for user_id
            if recipient_col:
                recipient_val = fields.get(recipient_col)
                recipient_info = parse_personnel_field(recipient_val)
                if recipient_info:
                    r_user_id, _ = recipient_info
                    name_to_userid[name.strip().lower()] = r_user_id
                    continue

            # Fallback: look up in contact user list
            if user_map is None:
                try:
                    user_map = client.fetch_all_users()
                except Exception:
                    user_map = {}
            uid = user_map.get(name.strip().lower())
            if uid:
                name_to_userid[name.strip().lower()] = uid

    except Exception as e:
        logger.error(f"Error building TVV name→user_id map: {e}")

    logger.info(f"Built TVV name mapping with {len(name_to_userid)} entries.")
    return name_to_userid


def build_tvv_name_to_link_map(client: LarkClient) -> Dict[str, str]:
    """
    Build a mapping of TVV name (lowercase) → link_record_id from the dispatch table.
    Used for DuplexLink (type 21) fields where we need the record_id in the linked table
    (Tỷ lệ chuyển đổi) to write via API format [record_id].
    """
    name_to_link = {}
    try:
        records = client.list_records(config.TABLE_TVV_ID)
        
        all_keys = set()
        for rec in records:
            all_keys.update(rec.get("fields", {}).keys())
        
        # Find "Tư vấn viên" Link column
        tvv_link_col = None
        for k in all_keys:
            k_low = k.lower().strip()
            if "tư vấn" in k_low or "tu van" in k_low:
                tvv_link_col = k
                break
        
        # Find personnel column
        personnel_col = config.FIELD_TVV_USER if config.FIELD_TVV_USER in all_keys else None
        if not personnel_col:
            for k in all_keys:
                k_low = k.lower().strip()
                if k_low in ["nhân sự", "nhân viên", "tên", "họ tên"]:
                    personnel_col = k
                    break
        
        for rec in records:
            fields = rec.get("fields", {})
            
            # Get name
            person_val = fields.get(personnel_col) if personnel_col else None
            name = None
            if isinstance(person_val, list) and len(person_val) > 0:
                first = person_val[0]
                if isinstance(first, dict):
                    name = first.get("name", "").strip()
            elif isinstance(person_val, str):
                name = person_val.strip()
            
            if not name:
                continue
            
            # Get link_record_id from TVV link column
            if tvv_link_col:
                tvv_link_val = fields.get(tvv_link_col)
                link_rid = None
                if isinstance(tvv_link_val, list) and len(tvv_link_val) > 0:
                    first = tvv_link_val[0]
                    if isinstance(first, dict):
                        rids = first.get("record_ids", [])
                        if rids:
                            link_rid = rids[0]
                elif isinstance(tvv_link_val, dict):
                    rids = tvv_link_val.get("link_record_ids", []) or tvv_link_val.get("record_ids", [])
                    if rids:
                        link_rid = rids[0]
                
                if link_rid:
                    name_to_link[name.lower()] = link_rid
    
    except Exception as e:
        logger.error(f"Error building TVV name→link_record_id map: {e}")
    
    logger.info(f"Built TVV name→link map with {len(name_to_link)} entries.")
    return name_to_link


def assign_m0_lead_to_tvv(client: LarkClient, lead_record_id: str) -> Optional[Dict[str, Any]]:
    """
    Distribute a single M0 lead to the best available TVV.
    Handles 3 modes:
    1. TVV filled, Người nhận data empty → round-robin for Người nhận data by region
    2. Người nhận data filled, TVV empty → find TVV link by matching name
    3. Both empty → round-robin for Người nhận data + resolve TVV link by name
    """
    logger.info(f"Starting M0 distribution for Lead {lead_record_id}...")
    
    # 1. Fetch the lead details
    lead = client.get_record(config.TABLE_TIKTOK_ID, lead_record_id)
    if not lead:
        logger.error(f"Lead {lead_record_id} not found.")
        return None
        
    fields = lead.get("fields", {})
    
    # Check source and channel eligibility (only distribute Online - Digital MKT & Tiktok)
    if not is_eligible_for_distribution(fields):
        logger.info(f"Lead {lead_record_id} does not match Nguồn Data='Online - Digital MKT' and Kênh đăng ký='Tiktok'. Skipping.")
        return None
        
    status = fields.get(config.FIELD_TIKTOK_STATUS)
    
    # Check if status matches config value
    if status != config.VALUE_TIKTOK_STATUS_M0:
        logger.warning(f"Lead {lead_record_id} status is '{status}', not '{config.VALUE_TIKTOK_STATUS_M0}'. We will still proceed since webhook was triggered.")
    
    # Detect current state of TVV and Người nhận data fields
    tvv_field_value = fields.get(config.FIELD_TIKTOK_ASSIGNED_USER)
    recipient_field_value = fields.get(config.FIELD_TIKTOK_RECIPIENT_USER)
    tvv_empty = _is_field_empty(tvv_field_value)
    recipient_empty = _is_field_empty(recipient_field_value)
    
    if not tvv_empty and not recipient_empty:
        logger.info(f"Lead {lead_record_id} already has both TVV and Người nhận data. Skipping.")
        return None
    
    lead_region = normalize_region(fields.get(config.FIELD_TIKTOK_REGION, ""))
    callback_time = fields.get(config.FIELD_TIKTOK_CALLBACK_TIME)
    current_time_ms = int(time.time() * 1000)
    target_callback_time = callback_time if callback_time is not None else current_time_ms
    
    logger.info(f"Lead Region: {lead_region}, Callback Time: {callback_time}, TVV empty: {tvv_empty}, Recipient empty: {recipient_empty}")
    
    update_fields = {}
    result_info = None
    
    if not tvv_empty and recipient_empty:
        # ── Mode 1: TVV filled, Người nhận data empty → round-robin by region ──
        logger.info(f"Mode 1 (mirror): TVV already filled, selecting Người nhận data by round-robin for Lead {lead_record_id}")
        active_tvvs = fetch_active_agents(client, "TVV")
        if not active_tvvs:
            logger.error("No active agents found. Cannot fill Người nhận data.")
            return None
        today_schedule = fetch_today_schedule(client)
        selected, final_cb = select_best_tvv_for_lead(
            lead_region, target_callback_time, active_tvvs, today_schedule
        )
        if selected:
            recipient_uid = selected.get("recipient_user_id") or selected["user_id"]
            update_fields = {
                config.FIELD_TIKTOK_RECIPIENT_USER: [{"id": recipient_uid}],
                config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
            }
            if final_cb != callback_time:
                update_fields[config.FIELD_TIKTOK_CALLBACK_TIME] = final_cb
            result_info = {"name": selected["name"], "user_id": recipient_uid}
            
    elif tvv_empty and not recipient_empty:
        # ── Mode 2: Người nhận data filled, TVV empty → find TVV link by name ──
        logger.info(f"Mode 2 (reverse-mirror): Người nhận data filled, finding TVV link for Lead {lead_record_id}")
        person_info = parse_personnel_field(recipient_field_value)
        if person_info:
            user_id, person_name = person_info
            if person_name:
                field_type = client.get_field_type(
                    config.TABLE_TIKTOK_ID, config.FIELD_TIKTOK_ASSIGNED_USER
                )
                if field_type == 18:
                    # Link field (one-way SingleLink) cannot be written via API
                    logger.info(
                        f"Mode 2: TVV Link field (type 18) cannot be written via API for lead {lead_record_id}. "
                        f"Người nhận data already filled with '{person_name}'. Skipping TVV link fill."
                    )
                elif field_type == 21:
                    # DuplexLink (two-way) → format: [record_id]
                    # Build name→link_record_id map to find the right record
                    tvv_name_map = build_tvv_name_to_link_map(client)
                    link_rid = tvv_name_map.get(person_name.strip().lower())
                    if link_rid:
                        update_fields = {
                            config.FIELD_TIKTOK_ASSIGNED_USER: [link_rid],
                            config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
                        }
                        result_info = {"name": person_name, "user_id": user_id}
                        logger.info(f"Mode 2: Filled TVV DuplexLink for lead {lead_record_id} → {person_name} ({link_rid})")
                    else:
                        logger.warning(f"Mode 2: Could not find link record for '{person_name}'. Skipping TVV fill.")
                elif field_type == 11:
                    update_fields = {
                        config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": user_id}],
                        config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
                    }
                    result_info = {"name": person_name, "user_id": user_id}
            else:
                logger.warning(f"Could not extract person name from Người nhận data for lead {lead_record_id}")
        else:
            logger.warning(f"Could not parse Người nhận data person info for lead {lead_record_id}")
                    
    else:
        # ── Mode 3: Both empty → round-robin for Người nhận data + TVV link ──
        logger.info(f"Mode 3 (round-robin): Both empty, selecting for Lead {lead_record_id}")
        active_tvvs = fetch_active_agents(client, "TVV")
        if not active_tvvs:
            logger.error("No active TVVs found today. Cannot distribute lead.")
            return None
        today_schedule = fetch_today_schedule(client)
        selected, final_cb = select_best_tvv_for_lead(
            lead_region, target_callback_time, active_tvvs, today_schedule
        )
        if selected:
            recipient_uid = selected.get("recipient_user_id") or selected["user_id"]
            update_fields = {
                config.FIELD_TIKTOK_RECIPIENT_USER: [{"id": recipient_uid}],
                config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
            }
            # Fill TVV field (Link or Person)
            field_type = client.get_field_type(
                config.TABLE_TIKTOK_ID, config.FIELD_TIKTOK_ASSIGNED_USER
            )
            if field_type == 18:
                # Link field (one-way SingleLink) cannot be written via API
                logger.info(
                    f"Skipping TVV Link field (type 18) for Lead {lead_record_id} "
                    f"→ {selected['name']}. Only filling 'Người nhận data'."
                )
            elif field_type == 21:
                # DuplexLink (two-way) → format: [record_id]
                linked_record_id = selected.get("tvv_link_record_id")
                if linked_record_id:
                    update_fields[config.FIELD_TIKTOK_ASSIGNED_USER] = [linked_record_id]
                    logger.info(f"Filled TVV DuplexLink for Lead {lead_record_id} → {selected['name']} ({linked_record_id})")
                else:
                    logger.warning(f"No tvv_link_record_id for {selected['name']}. Skipping TVV fill.")
            elif field_type == 11:
                update_fields[config.FIELD_TIKTOK_ASSIGNED_USER] = [{"id": recipient_uid}]
            elif field_type is None:
                # Fallback to Person format
                update_fields[config.FIELD_TIKTOK_ASSIGNED_USER] = [{"id": recipient_uid}]
            
            if final_cb != callback_time:
                update_fields[config.FIELD_TIKTOK_CALLBACK_TIME] = final_cb
            result_info = selected
    
    # Write update to Lark
    if update_fields:
        try:
            client.update_record(config.TABLE_TIKTOK_ID, lead_record_id, update_fields)
            logger.info(f"Successfully processed lead {lead_record_id}: {result_info}")
        except Exception as e:
            is_perm_err = False
            err_str = str(e)
            if "403" in err_str or "Permission denied" in err_str or "1254302" in err_str:
                is_perm_err = True
                
            if is_perm_err and config.FIELD_TIKTOK_ASSIGNED_USER in update_fields:
                logger.warning(
                    f"Update failed due to 403/Permission error. "
                    f"Attempting fallback update by excluding the '{config.FIELD_TIKTOK_ASSIGNED_USER}' field..."
                )
                fallback_fields = update_fields.copy()
                del fallback_fields[config.FIELD_TIKTOK_ASSIGNED_USER]
                if fallback_fields:
                    client.update_record(config.TABLE_TIKTOK_ID, lead_record_id, fallback_fields)
                    logger.info(f"Successfully processed lead {lead_record_id} using fallback (no 'Tư vấn viên' link).")
                else:
                    logger.info("Fallback update fields would be empty. Skipping update.")
            else:
                raise e
        return result_info
        
    return None

def _is_field_empty(field_value: Any) -> bool:
    """Check if a Lark field value is effectively empty.
    Handles: None, False, [], "", dict Link fields like {"link_record_ids": []},
    and DuplexLink (type 21) fields like {"record_ids": [], "table_id": "tblXXX"}
    or [{"record_ids": [], "table_id": "tblXXX"}].
    """
    if not field_value:
        return True
    if isinstance(field_value, list):
        if len(field_value) == 0:
            return True
        # DuplexLink can return a list of dicts like [{"record_ids": [], ...}]
        # Check if ALL items in the list are "empty link" dicts
        if all(isinstance(item, dict) for item in field_value):
            all_empty = True
            for item in field_value:
                if "id" in item:
                    all_empty = False
                    break
                rids = item.get("record_ids", item.get("link_record_ids"))
                if rids is not None:
                    if len(rids) > 0:
                        all_empty = False
                        break
                else:
                    if "table_id" in item:
                        # Empty link structure containing table_id but no record_ids
                        continue
                    # Dict without record_ids/link_record_ids or table_id -> treat as non-empty
                    all_empty = False
                    break
            if all_empty:
                return True
    if isinstance(field_value, str) and not field_value.strip():
        return True
    # Handle Link field (type 18): empty link returns dict like
    # {"link_record_ids": []} or {"link_record_ids": [], "table_id": "tblXXX"}
    # Handle DuplexLink (type 21): empty link returns dict like
    # {"record_ids": [], "table_id": "tblXXX"}
    if isinstance(field_value, dict):
        link_ids = field_value.get("link_record_ids")
        if link_ids is not None:
            return len(link_ids) == 0
        # DuplexLink uses "record_ids" key
        record_ids = field_value.get("record_ids")
        if record_ids is not None:
            return len(record_ids) == 0
        # Also handle {"text": ""} or {"text_arr": []} etc.
        text = field_value.get("text")
        if text is not None:
            return not str(text).strip()
        text_arr = field_value.get("text_arr")
        if text_arr is not None:
            return len(text_arr) == 0
    return False


def resolve_tvv_link_record_id(
    client: LarkClient,
    tvv_name: str,
    _cache: Dict[str, Any] = {}
) -> Optional[str]:
    """
    Find the record_id of a TVV in the linked table (Tỷ lệ chuyển đổi)
    by matching name. Uses the link field's metadata to discover the
    linked table, then searches for the matching record.
    
    Returns the record_id in the linked table, or None if not found.
    """
    # Get linked table info from field metadata (cached)
    if "linked_table_id" not in _cache or "linked_base_token" not in _cache:
        try:
            fields = client.list_fields(config.TABLE_TIKTOK_ID)
            for f in fields:
                if f.get("field_name") == config.FIELD_TIKTOK_ASSIGNED_USER and f.get("type") == 18:
                    prop = f.get("property", {})
                    linked_table_id = prop.get("table_id")
                    if linked_table_id:
                        _cache["linked_table_id"] = linked_table_id
                        # The linked table may be in the same base
                        _cache["linked_base_token"] = config.LARK_BASE_TOKEN
                        logger.info(f"Discovered linked table for TVV field: {linked_table_id}")
                    break
        except Exception as e:
            logger.warning(f"Could not discover linked table for TVV field: {e}")
            return None
    
    linked_table_id = _cache.get("linked_table_id")
    if not linked_table_id:
        logger.warning("No linked table found for TVV field. Cannot resolve link record.")
        return None
    
    # Build name → record_id map for linked table (cached)
    if "name_to_record_id" not in _cache:
        try:
            linked_records = client.list_records(linked_table_id)
            name_map = {}
            for rec in linked_records:
                rec_fields = rec.get("fields", {})
                # Try common name columns in the linked table
                for name_col in ["Họ và tên nhân viên", "Họ và tên", "Họ tên", "Tên", "Nhân sự", "Tư vấn viên"]:
                    val = rec_fields.get(name_col)
                    if isinstance(val, str) and val.strip():
                        name_map[val.strip().lower()] = rec.get("record_id")
                        break
                    elif isinstance(val, list) and len(val) > 0:
                        # Person field
                        person = val[0] if isinstance(val[0], dict) else None
                        if person:
                            pname = person.get("name", "").strip()
                            if pname:
                                name_map[pname.lower()] = rec.get("record_id")
                                break
            _cache["name_to_record_id"] = name_map
            logger.info(f"Built linked table name map with {len(name_map)} entries.")
        except Exception as e:
            logger.warning(f"Error building linked table name map: {e}")
            _cache["name_to_record_id"] = {}
    
    name_map = _cache.get("name_to_record_id", {})
    record_id = name_map.get(tvv_name.strip().lower())
    if record_id:
        logger.info(f"Resolved TVV '{tvv_name}' to linked record_id '{record_id}'.")
    else:
        logger.warning(f"Could not find TVV '{tvv_name}' in linked table.")
    return record_id


def assign_m0_leads_batch(client: LarkClient, lead_records: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Distribute a batch of M0 leads to TVVs, supporting three modes:
    
    1. Mirror mode: If 'Tư vấn viên' (Link field) is already filled but
       'Người nhận data' is empty, select 'Người nhận data' via round-robin
       by region from active agents in the dispatch table.
    2. Reverse-mirror mode: If 'Người nhận data' is already filled but
       'Tư vấn viên' is empty, extract the person name, find the matching
       record in the linked table (Tỷ lệ chuyển đổi), and fill 'Tư vấn viên'
       as a one-way link.
    3. Round-robin mode: If both fields are empty, select 'Người nhận data'
       via round-robin by region from the dispatch table, then find matching
       TVV link by name from 'Tỷ lệ chuyển đổi'.
    
    Returns: List of tuples (lead_record_id, selected_tvv_dict)
    """
    if not lead_records:
        return []
        
    logger.info(f"Starting batch M0 distribution for {len(lead_records)} leads...")
    
    current_time_ms = int(time.time() * 1000)
    records_to_update = []
    assigned_results = []
    
    # Lazy-loaded shared state for mirror mode and round-robin mode
    active_tvvs = None
    today_schedule = None
    tvv_name_map = None  # For DuplexLink reverse-mirror: name → link_record_id
    
    # Separate leads into mirror-mode, reverse-mirror-mode, and round-robin-mode
    mirror_leads = []          # Has TVV, missing Người nhận data
    reverse_mirror_leads = []  # Has Người nhận data, missing TVV
    roundrobin_leads = []      # Missing both
    
    for lead in lead_records:
        fields = lead.get("fields", {})
        
        # Check source and channel eligibility (only distribute Online - Digital MKT & Tiktok)
        if not is_eligible_for_distribution(fields):
            logger.info(f"Batch: Lead {lead.get('record_id')} does not match Nguồn Data='Online - Digital MKT' and Kênh đăng ký='Tiktok'. Skipping.")
            continue
            
        tvv_field_value = fields.get(config.FIELD_TIKTOK_ASSIGNED_USER)
        recipient_field_value = fields.get(config.FIELD_TIKTOK_RECIPIENT_USER)
        
        tvv_empty = _is_field_empty(tvv_field_value)
        recipient_empty = _is_field_empty(recipient_field_value)
        
        if not tvv_empty and recipient_empty:
            # Mirror mode: TVV filled, Người nhận data missing
            tvv_name = extract_tvv_name_from_field(tvv_field_value)
            if tvv_name:
                mirror_leads.append((lead, tvv_name))
            else:
                roundrobin_leads.append(lead)
        elif tvv_empty and not recipient_empty:
            # Reverse-mirror mode: Người nhận data filled, TVV missing
            reverse_mirror_leads.append(lead)
        elif tvv_empty and recipient_empty:
            # Round-robin mode: both empty
            roundrobin_leads.append(lead)
        # else: both filled → skip (already fully assigned)
    
    logger.info(f"Leads: mirror={len(mirror_leads)}, reverse-mirror={len(reverse_mirror_leads)}, "
                f"round-robin={len(roundrobin_leads)}")
    
    # ── Mirror mode: TVV already assigned, fill Người nhận data via round-robin by region ──
    if mirror_leads:
        # Pre-fetch active agents and schedule (shared with round-robin if needed)
        if active_tvvs is None:
            active_tvvs = fetch_active_agents(client, "TVV")
        if today_schedule is None and active_tvvs:
            today_schedule = fetch_today_schedule(client)
        
        if not active_tvvs:
            logger.error("No active agents found. Cannot fill Người nhận data for mirror leads.")
        else:
            for lead, tvv_name in mirror_leads:
                lead_record_id = lead.get("record_id")
                fields = lead.get("fields", {})
                lead_region = normalize_region(fields.get(config.FIELD_TIKTOK_REGION, ""))
                callback_time = fields.get(config.FIELD_TIKTOK_CALLBACK_TIME)
                target_callback_time = callback_time if callback_time is not None else current_time_ms
                
                selected, final_cb = select_best_tvv_for_lead(
                    lead_region, target_callback_time, active_tvvs, today_schedule
                )
                
                if selected:
                    recipient_uid = selected.get("recipient_user_id") or selected["user_id"]
                    if not recipient_uid:
                        logger.warning(f"Mirror mode: Lead {lead_record_id} → selected TVV has no valid user_id. Skipping.")
                        continue
                    update_fields = {
                        config.FIELD_TIKTOK_RECIPIENT_USER: [{"id": recipient_uid}],
                        config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
                    }
                    if final_cb != callback_time:
                        update_fields[config.FIELD_TIKTOK_CALLBACK_TIME] = final_cb
                    
                    records_to_update.append({
                        "record_id": lead_record_id,
                        "fields": update_fields
                    })
                    
                    # Track in schedule for subsequent round-robin fairness
                    today_schedule.append({
                        "record_id": lead_record_id,
                        "assigned_user_id": recipient_uid,
                        "assigned_time": current_time_ms,
                        "callback_time": final_cb
                    })
                    
                    assigned_results.append((lead_record_id, {"name": selected["name"], "user_id": recipient_uid}))
                    logger.info(f"Mirror mode: Lead {lead_record_id} → Người nhận data = {selected['name']} ({recipient_uid}) [round-robin by region={lead_region}]")
                else:
                    logger.warning(f"Mirror mode: Could not select agent for lead {lead_record_id}. Skipping.")
    
    # ── Reverse-mirror mode: Người nhận data filled, TVV link missing ──
    if reverse_mirror_leads:
        # Clear the link record cache for each batch run
        link_cache = {}
        
        for lead in reverse_mirror_leads:
            lead_record_id = lead.get("record_id")
            fields = lead.get("fields", {})
            
            recipient_value = fields.get(config.FIELD_TIKTOK_RECIPIENT_USER)
            person_info = parse_personnel_field(recipient_value)
            
            if not person_info:
                logger.warning(f"Reverse-mirror: Lead {lead_record_id} has Người nhận data "
                             f"but cannot parse person info. Skipping.")
                continue
            
            user_id, person_name = person_info
            if not person_name:
                logger.warning(f"Reverse-mirror: Lead {lead_record_id} has Người nhận data "
                             f"but no person name. Skipping.")
                continue
            
            # Check if TVV field is a Link field (type 18)
            field_type = client.get_field_type(
                config.TABLE_TIKTOK_ID, config.FIELD_TIKTOK_ASSIGNED_USER
            )
            
            if field_type == 18:
                # Link field (one-way SingleLink) cannot be written via API
                logger.info(
                    f"Reverse-mirror: TVV Link field (type 18) cannot be written via API for lead {lead_record_id}. "
                    f"Người nhận data already filled with '{person_name}'. Skipping."
                )
            elif field_type == 21:
                # DuplexLink (two-way) → format: [record_id]
                if tvv_name_map is None:
                    tvv_name_map = build_tvv_name_to_link_map(client)
                link_rid = tvv_name_map.get(person_name.strip().lower())
                if link_rid:
                    update_fields = {
                        config.FIELD_TIKTOK_ASSIGNED_USER: [link_rid],
                        config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
                    }
                    records_to_update.append({
                        "record_id": lead_record_id,
                        "fields": update_fields
                    })
                    assigned_results.append((lead_record_id, {"name": person_name, "user_id": user_id}))
                    logger.info(f"Reverse-mirror: Lead {lead_record_id} → TVV DuplexLink = {person_name} ({link_rid})")
                else:
                    logger.warning(f"Reverse-mirror: Could not find link record for '{person_name}'. Skipping.")
            elif field_type == 11:
                # Person field: fill directly with user_id
                update_fields = {
                    config.FIELD_TIKTOK_ASSIGNED_USER: [{"id": user_id}],
                    config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
                }
                records_to_update.append({
                    "record_id": lead_record_id,
                    "fields": update_fields
                })
                assigned_results.append((lead_record_id, {"name": person_name, "user_id": user_id}))
                logger.info(f"Reverse-mirror: Lead {lead_record_id} → TVV person = {person_name} ({user_id})")
            else:
                logger.warning(f"Reverse-mirror: TVV field type is {field_type}, unsupported. Skipping lead {lead_record_id}.")
    
    # ── Round-robin mode: both fields empty, use standard selection ──
    if roundrobin_leads:
        # Reuse active agents and schedule from mirror mode if already fetched
        if active_tvvs is None:
            active_tvvs = fetch_active_agents(client, "TVV")
        if today_schedule is None and active_tvvs:
            today_schedule = fetch_today_schedule(client)
        
        if not active_tvvs:
            logger.error("No active TVVs found today. Cannot distribute remaining leads via round-robin.")
        else:
            # Cache for link resolution across all round-robin leads
            rr_link_cache = {}
            
            for lead in roundrobin_leads:
                lead_record_id = lead.get("record_id")
                fields = lead.get("fields", {})
                
                lead_region = normalize_region(fields.get(config.FIELD_TIKTOK_REGION, ""))
                callback_time = fields.get(config.FIELD_TIKTOK_CALLBACK_TIME)
                target_callback_time = callback_time if callback_time is not None else current_time_ms
                
                selected_tvv, final_callback_time = select_best_tvv_for_lead(
                    lead_region, target_callback_time, active_tvvs, today_schedule
                )
                
                if selected_tvv:
                    recipient_uid = selected_tvv.get("recipient_user_id") or selected_tvv["user_id"]
                    if not recipient_uid:
                        logger.warning(f"Round-robin: Lead {lead_record_id} → selected TVV has no valid user_id. Skipping.")
                        continue
                    update_fields = {
                        config.FIELD_TIKTOK_RECIPIENT_USER: [{"id": recipient_uid}],
                        config.FIELD_TIKTOK_ASSIGNED_TIME: current_time_ms,
                    }
                    
                    # Fill TVV field (Link or Person)
                    field_type = client.get_field_type(
                        config.TABLE_TIKTOK_ID, config.FIELD_TIKTOK_ASSIGNED_USER
                    )
                    if field_type == 18:
                        # Link field (one-way SingleLink) cannot be written via API
                        logger.info(
                            f"Round-robin: Skipping TVV Link field (type 18) for Lead {lead_record_id} "
                            f"→ {selected_tvv['name']}. Only filling 'Người nhận data'."
                        )
                    elif field_type == 21:
                        # DuplexLink (two-way) → format: [record_id]
                        linked_record_id = selected_tvv.get("tvv_link_record_id")
                        if linked_record_id:
                            update_fields[config.FIELD_TIKTOK_ASSIGNED_USER] = [linked_record_id]
                            logger.info(f"Round-robin: Filled TVV DuplexLink for Lead {lead_record_id} → {selected_tvv['name']} ({linked_record_id})")
                        else:
                            logger.warning(f"Round-robin: No tvv_link_record_id for {selected_tvv['name']}. Skipping TVV fill.")
                    elif field_type == 11:
                        update_fields[config.FIELD_TIKTOK_ASSIGNED_USER] = [{"id": recipient_uid}]
                    elif field_type is None:
                        # Fallback to Person format
                        update_fields[config.FIELD_TIKTOK_ASSIGNED_USER] = [{"id": recipient_uid}]
                    
                    if final_callback_time != callback_time:
                        update_fields[config.FIELD_TIKTOK_CALLBACK_TIME] = final_callback_time
                        
                    records_to_update.append({
                        "record_id": lead_record_id,
                        "fields": update_fields
                    })
                    
                    # Append this assignment in-memory to affect subsequent assignments
                    today_schedule.append({
                        "record_id": lead_record_id,
                        "assigned_user_id": recipient_uid,
                        "assigned_time": current_time_ms,
                        "callback_time": final_callback_time
                    })
                    
                    assigned_results.append((lead_record_id, selected_tvv))
                    logger.info(f"Round-robin: Lead {lead_record_id} → Người nhận data={selected_tvv['name']} ({recipient_uid})")
    
    # ── Batch write to Lark ──
    if records_to_update:
        logger.info(f"Performing batch update in Lark for {len(records_to_update)} records...")
        try:
            client.batch_update_records(config.TABLE_TIKTOK_ID, records_to_update)
            logger.info("Successfully updated batch records.")
        except Exception as e:
            is_perm_err = False
            err_str = str(e)
            if "403" in err_str or "Permission denied" in err_str or "1254302" in err_str:
                is_perm_err = True
                
            if is_perm_err:
                logger.warning(
                    f"Batch update failed due to 403/Permission error. This usually happens when the "
                    f"Duplex Link column '{config.FIELD_TIKTOK_ASSIGNED_USER}' connects to a table in another "
                    f"base where the Lark App has not been granted Editor permissions. "
                    f"Attempting fallback update by excluding the '{config.FIELD_TIKTOK_ASSIGNED_USER}' field..."
                )
                fallback_records = []
                for rec in records_to_update:
                    f_fields = rec.get("fields", {}).copy()
                    if config.FIELD_TIKTOK_ASSIGNED_USER in f_fields:
                        del f_fields[config.FIELD_TIKTOK_ASSIGNED_USER]
                    fallback_records.append({
                        "record_id": rec["record_id"],
                        "fields": f_fields
                    })
                try:
                    client.batch_update_records(config.TABLE_TIKTOK_ID, fallback_records)
                    logger.info("Successfully completed fallback update (assigned 'Người nhận data' only).")
                except Exception as fallback_err:
                    logger.error(f"Fallback update also failed: {fallback_err}")
                    raise fallback_err
            else:
                raise e
        
    return assigned_results

