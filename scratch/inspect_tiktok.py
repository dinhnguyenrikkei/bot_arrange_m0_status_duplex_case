import requests
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from lark_client import LarkClient

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    client = LarkClient()
    token = client.get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{config.LARK_BASE_TOKEN}/tables/{config.TABLE_TIKTOK_ID}/records"
    params = {"view_id": "vewAGVc1MY"}
    r = requests.get(url, headers=headers, params=params, timeout=10)
    print("TikTok Records API Response Status:", r.status_code)
    try:
        res = r.json()
        print("Code:", res.get("code"))
        print("Msg:", res.get("msg"))
        items = res.get("data", {}).get("items", [])
        print("Number of records:", len(items))
        if items:
            print("First record:", json.dumps(items[0], indent=2, ensure_ascii=False))
    except Exception as e:
        print("Error parsing json:", e)
        print("Raw text:", r.text[:1000])

if __name__ == "__main__":
    main()
