import os
import sys
import re
import requests
from typing import Optional
from dotenv import load_dotenv

# Path to .env file relative to the executable or the script
if getattr(sys, 'frozen', False):
    ENV_FILE_PATH = os.path.join(os.path.dirname(sys.executable), ".env")
else:
    ENV_FILE_PATH = ".env"

# Global config variables
LARK_APP_ID = ""
LARK_APP_SECRET = ""
LINK_TABLE_TIKTOK = ""
LINK_TABLE_TVV = ""
LARK_BASE_TOKEN = ""
LARK_BASE_TOKEN_TVV = ""
TABLE_TIKTOK_ID = ""
TABLE_TVV_ID = ""
FIELD_TIKTOK_STATUS = ""
VALUE_TIKTOK_STATUS_M0 = ""
FIELD_TIKTOK_REGION = ""
FIELD_TIKTOK_CALLBACK_TIME = ""
FIELD_TIKTOK_ASSIGNED_USER = ""
FIELD_TIKTOK_RECIPIENT_USER = ""
FIELD_TIKTOK_ASSIGNED_TIME = ""
FIELD_TVV_USER = ""
FIELD_TVV_ACTIVE = ""
FIELD_TVV_REGION = ""
FIELD_TVV_ROLE = ""
MAX_ASSIGNMENTS_PER_DAY = 2
COOLDOWN_MINUTES_BETWEEN_CALLS = 15
SYNC_INTERVAL_SECONDS = 60
PORT = 8000
BOT_ACTIVE = False

def reload_config(dotenv_path=None):
    """Reload environment variables from .env file and update globals."""
    global LARK_APP_ID, LARK_APP_SECRET, LARK_BASE_TOKEN, LARK_BASE_TOKEN_TVV
    global LINK_TABLE_TIKTOK, LINK_TABLE_TVV
    global TABLE_TIKTOK_ID, TABLE_TVV_ID
    global FIELD_TIKTOK_STATUS, VALUE_TIKTOK_STATUS_M0, FIELD_TIKTOK_REGION, FIELD_TIKTOK_CALLBACK_TIME, FIELD_TIKTOK_ASSIGNED_USER, FIELD_TIKTOK_RECIPIENT_USER, FIELD_TIKTOK_ASSIGNED_TIME
    global FIELD_TVV_USER, FIELD_TVV_ACTIVE, FIELD_TVV_REGION, FIELD_TVV_ROLE
    global MAX_ASSIGNMENTS_PER_DAY, COOLDOWN_MINUTES_BETWEEN_CALLS, SYNC_INTERVAL_SECONDS, PORT, BOT_ACTIVE

    if dotenv_path is None:
        dotenv_path = ENV_FILE_PATH

    load_dotenv(dotenv_path=dotenv_path, override=True)

    LARK_APP_ID = os.getenv("LARK_APP_ID", "")
    LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")
    LINK_TABLE_TIKTOK = os.getenv("LINK_TABLE_TIKTOK", "")
    LINK_TABLE_TVV = os.getenv("LINK_TABLE_TVV", "")
    LARK_BASE_TOKEN = os.getenv("LARK_BASE_TOKEN", "")
    LARK_BASE_TOKEN_TVV = os.getenv("LARK_BASE_TOKEN_TVV", "")

    TABLE_TIKTOK_ID = os.getenv("TABLE_TIKTOK_ID", "")
    TABLE_TVV_ID = os.getenv("TABLE_TVV_ID", "")

    FIELD_TIKTOK_STATUS = os.getenv("FIELD_TIKTOK_STATUS") or "Trạng thái"
    VALUE_TIKTOK_STATUS_M0 = os.getenv("VALUE_TIKTOK_STATUS_M0") or "M0-Data đã claim"
    FIELD_TIKTOK_REGION = os.getenv("FIELD_TIKTOK_REGION") or "Khu vực"
    FIELD_TIKTOK_CALLBACK_TIME = os.getenv("FIELD_TIKTOK_CALLBACK_TIME") or "Hẹn gọi lại"
    FIELD_TIKTOK_ASSIGNED_USER = os.getenv("FIELD_TIKTOK_ASSIGNED_USER") or "Tư vấn viên"
    FIELD_TIKTOK_RECIPIENT_USER = os.getenv("FIELD_TIKTOK_RECIPIENT_USER") or "Người nhận data"
    FIELD_TIKTOK_ASSIGNED_TIME = os.getenv("FIELD_TIKTOK_ASSIGNED_TIME") or "Thời gian phân phối"

    FIELD_TVV_USER = os.getenv("FIELD_TVV_USER") or "Nhân sự"
    FIELD_TVV_ACTIVE = os.getenv("FIELD_TVV_ACTIVE") or "Đi làm hôm nay"
    FIELD_TVV_REGION = os.getenv("FIELD_TVV_REGION") or "Khu vực hoạt động"
    FIELD_TVV_ROLE = os.getenv("FIELD_TVV_ROLE") or "Vai trò"

    MAX_ASSIGNMENTS_PER_DAY = int(os.getenv("MAX_ASSIGNMENTS_PER_DAY", "2"))
    COOLDOWN_MINUTES_BETWEEN_CALLS = int(os.getenv("COOLDOWN_MINUTES_BETWEEN_CALLS", "15"))
    SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "60"))
    PORT = int(os.getenv("PORT", "8000"))
    BOT_ACTIVE = os.getenv("BOT_ACTIVE", "False").lower() in ("true", "1", "yes")

# Initialize variables on load
reload_config()

def validate_config():
    """Verify that all required environment variables are set."""
    missing = []
    if not LARK_APP_ID: missing.append("LARK_APP_ID")
    if not LARK_APP_SECRET: missing.append("LARK_APP_SECRET")
    if not LARK_BASE_TOKEN: missing.append("LARK_BASE_TOKEN")
    if not TABLE_TIKTOK_ID: missing.append("TABLE_TIKTOK_ID")
    if not TABLE_TVV_ID: missing.append("TABLE_TVV_ID")
    
    if missing:
        raise ValueError(f"Missing required environment variables in .env: {', '.join(missing)}")

def get_current_env_values() -> dict:
    """Read .env file directly and return keys/values."""
    values = {
        "LARK_APP_ID": "",
        "LARK_APP_SECRET": "",
        "LINK_TABLE_TIKTOK": "",
        "LINK_TABLE_TVV": "",
        "LARK_BASE_TOKEN": "",
        "LARK_BASE_TOKEN_TVV": "",
        "TABLE_TIKTOK_ID": "",
        "TABLE_TVV_ID": "",
        "MAX_ASSIGNMENTS_PER_DAY": "2",
        "COOLDOWN_MINUTES_BETWEEN_CALLS": "15",
        "SYNC_INTERVAL_SECONDS": "60",
        "PORT": "8000",
        "BOT_ACTIVE": "False",
        "FIELD_TIKTOK_STATUS": "Trạng thái",
        "VALUE_TIKTOK_STATUS_M0": "M0-Data đã claim",
        "FIELD_TIKTOK_REGION": "Khu vực",
        "FIELD_TIKTOK_CALLBACK_TIME": "Hẹn gọi lại",
        "FIELD_TIKTOK_ASSIGNED_USER": "Tư vấn viên",
        "FIELD_TIKTOK_RECIPIENT_USER": "Người nhận data",
        "FIELD_TIKTOK_ASSIGNED_TIME": "Thời gian phân phối",
        "FIELD_TVV_USER": "Nhân sự",
        "FIELD_TVV_ACTIVE": "Đi làm hôm nay",
        "FIELD_TVV_REGION": "Khu vực hoạt động",
        "FIELD_TVV_ROLE": "Vai trò"
    }
    
    if os.path.exists(ENV_FILE_PATH):
        with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    parts = line.split("=", 1)
                    k = parts[0].strip()
                    v = parts[1].strip().strip('"').strip("'")
                    if k in values:
                        values[k] = v
    else:
        # Fallback to current config values
        values["LARK_APP_ID"] = LARK_APP_ID
        values["LARK_APP_SECRET"] = LARK_APP_SECRET
        values["LINK_TABLE_TIKTOK"] = LINK_TABLE_TIKTOK
        values["LINK_TABLE_TVV"] = LINK_TABLE_TVV
        values["LARK_BASE_TOKEN"] = LARK_BASE_TOKEN
        values["LARK_BASE_TOKEN_TVV"] = LARK_BASE_TOKEN_TVV
        values["TABLE_TIKTOK_ID"] = TABLE_TIKTOK_ID
        values["TABLE_TVV_ID"] = TABLE_TVV_ID
        values["MAX_ASSIGNMENTS_PER_DAY"] = str(MAX_ASSIGNMENTS_PER_DAY)
        values["COOLDOWN_MINUTES_BETWEEN_CALLS"] = str(COOLDOWN_MINUTES_BETWEEN_CALLS)
        values["SYNC_INTERVAL_SECONDS"] = str(SYNC_INTERVAL_SECONDS)
        values["PORT"] = str(PORT)
        values["BOT_ACTIVE"] = str(BOT_ACTIVE)
        values["FIELD_TIKTOK_STATUS"] = FIELD_TIKTOK_STATUS
        values["VALUE_TIKTOK_STATUS_M0"] = VALUE_TIKTOK_STATUS_M0
        values["FIELD_TIKTOK_REGION"] = FIELD_TIKTOK_REGION
        values["FIELD_TIKTOK_CALLBACK_TIME"] = FIELD_TIKTOK_CALLBACK_TIME
        values["FIELD_TIKTOK_ASSIGNED_USER"] = FIELD_TIKTOK_ASSIGNED_USER
        values["FIELD_TIKTOK_RECIPIENT_USER"] = FIELD_TIKTOK_RECIPIENT_USER
        values["FIELD_TIKTOK_ASSIGNED_TIME"] = FIELD_TIKTOK_ASSIGNED_TIME
        values["FIELD_TVV_USER"] = FIELD_TVV_USER
        values["FIELD_TVV_ACTIVE"] = FIELD_TVV_ACTIVE
        values["FIELD_TVV_REGION"] = FIELD_TVV_REGION
        values["FIELD_TVV_ROLE"] = FIELD_TVV_ROLE
        
    return values

def discover_table_id(app_id: str, app_secret: str, base_token: str, table_type: str) -> Optional[str]:
    """
    Query Lark API to list all tables in a base and try to auto-detect the correct Table ID
    based on table name keywords.
    """
    if not app_id or not app_secret or not base_token:
        return None
    try:
        # Get tenant access token
        url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
        payload = {"app_id": app_id, "app_secret": app_secret}
        res = requests.post(url, json=payload, timeout=10)
        res_data = res.json()
        if res_data.get("code") != 0:
            return None
        token = res_data.get("tenant_access_token")
        if not token:
            return None
        
        # Get list of tables
        tables_url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables"
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(tables_url, headers=headers, timeout=10)
        data = r.json()
        if data.get("code") == 0:
            tables = data.get("data", {}).get("items", [])
            if not tables:
                return None
            
            # If only 1 table exists in the Bitable, auto-select it
            if len(tables) == 1:
                return tables[0].get("table_id")
                
            # Otherwise, check name keywords
            if table_type == "tiktok":
                # Look for tiktok/lead/customer
                for t in tables:
                    name_lower = t.get("name", "").lower()
                    if any(kw in name_lower for kw in ["tiktok", "customer", "lead", "khách", "data"]):
                        return t.get("table_id")
            elif table_type == "tvv":
                # Look for tvv/tư vấn/nhân sự
                for t in tables:
                    name_lower = t.get("name", "").lower()
                    if any(kw in name_lower for kw in ["tvv", "tư vấn", "nhân sự", "agent", "member", "staff"]):
                        return t.get("table_id")
            
            # Fallback to the first table in the list
            return tables[0].get("table_id")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to auto-discover table ID for base {base_token}: {e}")
    return None

def get_bitable_token_from_sheets_api(app_id: str, app_secret: str, spreadsheet_token: str) -> Optional[str]:
    """
    Get the underlying Bitable token from a Lark spreadsheet token.
    Requires that the app is added as a collaborator to the spreadsheet.
    """
    if not app_id or not app_secret or not spreadsheet_token:
        return None
    try:
        # Get tenant access token
        url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
        payload = {"app_id": app_id, "app_secret": app_secret}
        res = requests.post(url, json=payload, timeout=10)
        res_data = res.json()
        if res_data.get("code") != 0:
            return None
        token = res_data.get("tenant_access_token")
        if not token:
            return None
            
        # Get spreadsheet metainfo
        meta_url = f"https://open.larksuite.com/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo"
        headers = {"Authorization": f"Bearer {token}"}
        meta_res = requests.get(meta_url, headers=headers, timeout=10)
        data = meta_res.json()
        
        if data.get("code") == 0:
            block_info_list = data.get("data", {}).get("blockInfo", [])
            for block in block_info_list:
                if block.get("blockType") == "BITABLE_BLOCK":
                    b_token = block.get("blockToken")
                    if b_token:
                        if "_" in b_token:
                            return b_token.split("_")[0]
                        return b_token
                        
            # Fallback to check sheets properties
            sheets = data.get("data", {}).get("sheets", [])
            for sheet in sheets:
                block_info = sheet.get("blockInfo")
                if block_info and block_info.get("blockType") == "BITABLE_BLOCK":
                    b_token = block_info.get("blockToken")
                    if b_token:
                        if "_" in b_token:
                            return b_token.split("_")[0]
                        return b_token
        elif data.get("code") == 91402 or "NOTEXIST" in data.get("msg", ""):
            # Permission or not shared error
            logging.getLogger(__name__).error(
                f"\n[ERROR] Khong tim thay hoac khong co quyen truy cap Spreadsheet '{spreadsheet_token}'.\n"
                f"VUI LONG CHIA SE TRANG TINH NAY cho ung dung cua ban (App ID: {app_id}) bang cach:\n"
                f"1. Mo trang tinh (spreadsheet) tren Lark.\n"
                f"2. Nhan 'Chia se' (Share) o goc tren bên phai.\n"
                f"3. Them ung dung '{app_id}' (hoac ten app cua ban) vao voi quyen 'Co the xem' (Can View) hoac 'Co the sua' (Can Edit).\n"
            )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error fetching bitable app_token for spreadsheet {spreadsheet_token}: {e}")
    return None

def update_env_values(new_values: dict):
    """Update .env file with new values and reload config."""
    # Filter out None values to prevent writing "None" to .env
    new_values = {k: v for k, v in new_values.items() if v is not None}
    
    app_id = new_values.get("LARK_APP_ID", LARK_APP_ID)
    app_secret = new_values.get("LARK_APP_SECRET", LARK_APP_SECRET)

    # Parse LINK_TABLE_TIKTOK for base token and table ID
    link_tiktok = new_values.get("LINK_TABLE_TIKTOK", "")
    if link_tiktok:
        base_match = re.search(r'/(?:base|sheets)/([a-zA-Z0-9]+)', link_tiktok)
        table_match = re.search(r'[?&]table=([a-zA-Z0-9]+)', link_tiktok) or re.search(r'/table/([a-zA-Z0-9]+)', link_tiktok)
        if base_match:
            token_extracted = base_match.group(1)
            # If it's a sheets token, try to discover the real bitable token
            if "/sheets/" in link_tiktok:
                bitable_token = get_bitable_token_from_sheets_api(app_id, app_secret, token_extracted)
                if bitable_token:
                    new_values["LARK_BASE_TOKEN"] = bitable_token
                else:
                    new_values["LARK_BASE_TOKEN"] = token_extracted
            else:
                new_values["LARK_BASE_TOKEN"] = token_extracted
        if table_match:
            new_values["TABLE_TIKTOK_ID"] = table_match.group(1)
        else:
            # Table ID not in URL, try auto-discovery
            base_token = new_values.get("LARK_BASE_TOKEN")
            if base_token:
                discovered_id = discover_table_id(app_id, app_secret, base_token, "tiktok")
                if discovered_id:
                    new_values["TABLE_TIKTOK_ID"] = discovered_id

    # Parse LINK_TABLE_TVV for base token and table ID
    link_tvv = new_values.get("LINK_TABLE_TVV", "")
    if link_tvv:
        base_match = re.search(r'/(?:base|sheets)/([a-zA-Z0-9]+)', link_tvv)
        table_match = re.search(r'[?&]table=([a-zA-Z0-9]+)', link_tvv) or re.search(r'/table/([a-zA-Z0-9]+)', link_tvv)
        if base_match:
            token_extracted = base_match.group(1)
            # If it's a sheets token, try to discover the real bitable token
            if "/sheets/" in link_tvv:
                bitable_token = get_bitable_token_from_sheets_api(app_id, app_secret, token_extracted)
                if bitable_token:
                    new_values["LARK_BASE_TOKEN_TVV"] = bitable_token
                else:
                    new_values["LARK_BASE_TOKEN_TVV"] = token_extracted
            else:
                new_values["LARK_BASE_TOKEN_TVV"] = token_extracted
        if table_match:
            new_values["TABLE_TVV_ID"] = table_match.group(1)
        else:
            # Table ID not in URL, try auto-discovery
            base_token_tvv = new_values.get("LARK_BASE_TOKEN_TVV")
            if base_token_tvv:
                discovered_id = discover_table_id(app_id, app_secret, base_token_tvv, "tvv")
                if discovered_id:
                    new_values["TABLE_TVV_ID"] = discovered_id

    lines = []
    existing_keys = set()
    
    if os.path.exists(ENV_FILE_PATH):
        with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    updated_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            parts = stripped.split("=", 1)
            k = parts[0].strip()
            if k in new_values:
                updated_lines.append(f'{k}="{new_values[k]}"\n')
                existing_keys.add(k)
                continue
        updated_lines.append(line)
        
    # Append keys that were not in the file
    for k, v in new_values.items():
        if k not in existing_keys:
            updated_lines.append(f'{k}="{v}"\n')
            
    with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)
        
    # Reload config
    reload_config()
