import time
import logging
import requests
from typing import Dict, Any, List, Optional
import config

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class LarkClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._user_map_cache: Optional[Dict[str, str]] = None
        self._user_map_cache_expires_at: float = 0.0
        self._fields_cache: Dict[str, tuple] = {}  # table_id -> (expires_at, fields_list)

    @property
    def app_id(self) -> str:
        return config.LARK_APP_ID

    @property
    def app_secret(self) -> str:
        return config.LARK_APP_SECRET

    def _get_base_token(self, table_id: str) -> str:
        # If separate base token exists for TVV table, use it. Otherwise fall back to LARK_BASE_TOKEN.
        if table_id == config.TABLE_TVV_ID and config.LARK_BASE_TOKEN_TVV:
            return config.LARK_BASE_TOKEN_TVV
        return config.LARK_BASE_TOKEN

    def get_token(self) -> str:
        """Get the cached tenant_access_token or request a new one if expired."""
        current_time = time.time()
        # If token is still valid (with a 5-minute safety buffer)
        if self._token and current_time < self._token_expires_at - 300:
            return self._token

        url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            logger.info("Requesting new tenant_access_token...")
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 0:
                self._token = data.get("tenant_access_token")
                # expire_seconds = data.get("expire", 7200)
                # For safety, use 7200 or the API-provided expire time
                expire_seconds = data.get("expire", 7200)
                self._token_expires_at = current_time + expire_seconds
                logger.info("Successfully fetched tenant_access_token.")
                return self._token
            else:
                raise ValueError(f"Failed to get token from Lark: {data.get('msg')} (code: {data.get('code')})")
        except Exception as e:
            logger.error(f"Error fetching tenant_access_token: {e}")
            raise

    def get_headers(self) -> Dict[str, str]:
        """Get standard headers with the Bearer authorization token."""
        token = self.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }

    def list_records(self, table_id: str, filter_formula: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all records from a table, automatically handling pagination.
        
        :param table_id: Bitable table ID
        :param filter_formula: Optional filter formula query string
        :return: List of record dictionaries (containing record_id and fields)
        """
        base_token = self._get_base_token(table_id)
        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records"
        records = []
        page_token = None
        has_more = True
        
        while has_more:
            params = {
                "page_size": 500,
            }
            if page_token:
                params["page_token"] = page_token
            if filter_formula:
                params["filter"] = filter_formula

            headers = self.get_headers()
            
            if not params:
                params = {}
            params["user_id_type"] = "open_id"
            
            try:
                # Lark's List Records is GET
                # If we have a filter, we can pass it as a JSON payload or in the query.
                # Actually, standard GET request doesn't take a JSON body, but Lark's API accepts filter parameter.
                # If we need complex filtering, we will do it in-memory to prevent complex URL encoding and API mismatches.
                response = requests.get(url, headers=headers, params=params, timeout=30)
                if response.status_code != 200:
                    logger.error(f"HTTP Status {response.status_code} listing records from Lark: {response.text}")
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") == 0:
                    page_data = data.get("data", {})
                    items = page_data.get("items", [])
                    records.extend(items)
                    
                    has_more = page_data.get("has_more", False)
                    page_token = page_data.get("page_token")
                else:
                    raise ValueError(f"Error listing records: {data.get('msg')} (code: {data.get('code')})")
            except Exception as e:
                if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                    logger.error(f"Detailed HTTP Error response listing records: {e.response.text}")
                logger.error(f"Failed to list records for table {table_id}: {e}")
                raise
                
        return records

    def get_record(self, table_id: str, record_id: str) -> Dict[str, Any]:
        """
        Fetch a single record by its ID.
        """
        base_token = self._get_base_token(table_id)
        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}?user_id_type=open_id"
        headers = self.get_headers()
        try:
            logger.info(f"Fetching record {record_id} from table {table_id}...")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("record", {})
            else:
                raise ValueError(f"Failed to get record: {data.get('msg')} (code: {data.get('code')})")
        except Exception as e:
            logger.error(f"Error fetching record {record_id}: {e}")
            raise

    def update_record(self, table_id: str, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update fields of a single record.
        """
        base_token = self._get_base_token(table_id)
        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}"
        payload = {"fields": fields}
        headers = self.get_headers()
        
        try:
            logger.info(f"Updating record {record_id} in table {table_id}...")
            response = requests.put(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 0:
                logger.info(f"Successfully updated record {record_id}.")
                return data.get("data", {})
            else:
                raise ValueError(f"Failed to update record: {data.get('msg')} (code: {data.get('code')})")
        except Exception as e:
            logger.error(f"Error updating record {record_id}: {e}")
            raise

    def batch_update_records(self, table_id: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Batch update records. Max 500 records at a time.
        
        :param records: List of dicts, each with keys 'record_id' and 'fields'.
                        Example: [{'record_id': 'rec1', 'fields': {'Status': 'Completed'}}]
        """
        if not records:
            return {}
            
        base_token = self._get_base_token(table_id)
        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/batch_update?user_id_type=open_id"
        headers = self.get_headers()
        
        # Split into chunks of 500 records
        chunk_size = 500
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            payload = {"records": chunk}
            
            try:
                logger.info(f"Batch updating {len(chunk)} records in table {table_id}...")
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code != 200:
                    logger.error(f"HTTP Status {response.status_code} from Lark: {response.text}")
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") != 0:
                    raise ValueError(f"Failed to batch update records: {data.get('msg')} (code: {data.get('code')})")
            except Exception as e:
                if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                    logger.error(f"Detailed HTTP Error response: {e.response.text}")
                logger.error(f"Error batch updating records: {e}")
                raise
                
        logger.info(f"Successfully batch updated {len(records)} records.")
        return {"code": 0, "msg": "success"}

    def batch_create_records(self, table_id: str, records: List[Dict[str, Any]]) -> List[str]:
        """
        Batch create records. Max 500 records at a time.
        
        :param records: List of dicts, each with key 'fields'.
                        Example: [{'fields': {'Status': 'M0-Data đã claim', ...}}]
        :return: List of created record_ids
        """
        if not records:
            return []
            
        base_token = self._get_base_token(table_id)
        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/batch_create?user_id_type=open_id"
        headers = self.get_headers()
        created_ids = []
        
        # Split into chunks of 500 records
        chunk_size = 500
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            payload = {"records": chunk}
            
            try:
                logger.info(f"Batch creating {len(chunk)} records in table {table_id}...")
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") == 0:
                    items = data.get("data", {}).get("records", [])
                    for item in items:
                        rec_id = item.get("record_id")
                        if rec_id:
                            created_ids.append(rec_id)
                else:
                    raise ValueError(f"Failed to batch create records: {data.get('msg')} (code: {data.get('code')})")
            except Exception as e:
                logger.error(f"Error batch creating records: {e}")
                raise
                
        logger.info(f"Successfully batch created {len(created_ids)} records.")
        return created_ids

    def batch_delete_records(self, table_id: str, record_ids: List[str]) -> Dict[str, Any]:
        """
        Batch delete records. Max 500 records at a time.
        
        :param record_ids: List of record_id strings.
        """
        if not record_ids:
            return {}
            
        base_token = self._get_base_token(table_id)
        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/batch_delete"
        headers = self.get_headers()
        
        # Split into chunks of 500 records
        chunk_size = 500
        for i in range(0, len(record_ids), chunk_size):
            chunk = record_ids[i:i + chunk_size]
            payload = {"records": chunk}
            
            try:
                logger.info(f"Batch deleting {len(chunk)} records in table {table_id}...")
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") != 0:
                    raise ValueError(f"Failed to batch delete records: {data.get('msg')} (code: {data.get('code')})")
            except Exception as e:
                logger.error(f"Error batch deleting records: {e}")
                raise
                
        logger.info(f"Successfully batch deleted {len(record_ids)} records.")
        return {"code": 0, "msg": "success"}

    def list_fields(self, table_id: str) -> List[Dict[str, Any]]:
        """
        List all fields/columns of a Bitable table with caching (1 hour).
        Returns list of field dicts with keys: field_name, type, property, is_primary, etc.
        """
        current_time = time.time()
        cache_key = table_id
        if cache_key in self._fields_cache:
            expires_at, cached_fields = self._fields_cache[cache_key]
            if current_time < expires_at:
                return cached_fields

        base_token = self._get_base_token(table_id)
        url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/fields"
        headers = self.get_headers()
        fields = []
        page_token = None
        has_more = True

        while has_more:
            params = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token

            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if data.get("code") == 0:
                    page_data = data.get("data", {})
                    items = page_data.get("items", [])
                    fields.extend(items)
                    has_more = page_data.get("has_more", False)
                    page_token = page_data.get("page_token")
                else:
                    logger.warning(f"Failed to list fields for table {table_id}: {data.get('msg')} (code: {data.get('code')})")
                    break
            except Exception as e:
                logger.warning(f"Error listing fields for table {table_id}: {e}")
                break

        # Cache for 1 hour
        self._fields_cache[cache_key] = (current_time + 3600, fields)
        logger.info(f"Cached {len(fields)} field definitions for table {table_id}.")
        return fields

    def get_field_type(self, table_id: str, field_name: str) -> Optional[int]:
        """
        Get the Lark field type code for a specific field by name.
        Returns None if field not found or API error.
        Common types: 1=Text, 5=DateTime, 11=Person/User, 18=Link, 20=Formula.
        """
        try:
            fields = self.list_fields(table_id)
            for f in fields:
                if f.get("field_name") == field_name:
                    return f.get("type")
        except Exception as e:
            logger.warning(f"Could not detect field type for '{field_name}' in table {table_id}: {e}")
        return None

    def fetch_all_users(self, force_refresh: bool = False) -> Dict[str, str]:
        """
        Fetch all users within the app's contact scope and return a mapping of name -> open_id.
        """
        current_time = time.time()
        if not force_refresh and self._user_map_cache is not None and current_time < self._user_map_cache_expires_at:
            return self._user_map_cache

        url = "https://open.larksuite.com/open-apis/contact/v3/users"
        user_map = {}
        page_token = None
        has_more = True
        
        while has_more:
            params = {
                "page_size": 100,
            }
            if page_token:
                params["page_token"] = page_token
                
            headers = self.get_headers()
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") == 0:
                    page_data = data.get("data", {})
                    items = page_data.get("items", [])
                    for item in items:
                        name = item.get("name")
                        open_id = item.get("open_id")
                        if name and open_id:
                            user_map[name.strip().lower()] = open_id
                            
                    has_more = page_data.get("has_more", False)
                    page_token = page_data.get("page_token")
                else:
                    logger.warning(f"Failed to fetch users: {data.get('msg')} (code: {data.get('code')})")
                    break
            except Exception as e:
                logger.error(f"Error listing users: {e}")
                break
                
        self._user_map_cache = user_map
        self._user_map_cache_expires_at = current_time + 3600  # Cache for 1 hour
        return user_map

