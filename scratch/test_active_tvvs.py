import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from lark_client import LarkClient
from assigner import fetch_active_agents

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print("Testing active TVV agent fetching and dynamic column detection...")
    client = LarkClient()
    try:
        agents = fetch_active_agents(client, "TVV")
        print(f"Success! Found {len(agents)} active TVVs today:")
        print(json.dumps(agents, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error fetching active TVVs: {e}")

if __name__ == "__main__":
    main()
