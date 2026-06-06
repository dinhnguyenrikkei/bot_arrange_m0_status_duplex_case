import logging
import os
import sys
import asyncio
import collections
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import config
from lark_client import LarkClient
from assigner import assign_m0_lead_to_tvv, assign_t0_leads_to_tts, assign_m0_leads_batch, _is_field_empty

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# Set up log queue for UI console
log_queue = collections.deque(maxlen=50)

class QueueHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        log_queue.append(log_entry)

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Add queue handler to root logger to capture all module logs
queue_handler = QueueHandler()
queue_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(queue_handler)

app = FastAPI(title="Lark Bitable Lead Distributor", version="1.0.0")
lark_client = LarkClient()

# Security Token (optional, set in .env as WEBHOOK_TOKEN)
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")

class M0WebhookPayload(BaseModel):
    record_id: str

class ConfigPayload(BaseModel):
    LARK_APP_ID: str
    LARK_APP_SECRET: str
    LINK_TABLE_TIKTOK: str
    LINK_TABLE_TVV: str
    MAX_ASSIGNMENTS_PER_DAY: Optional[str] = None
    COOLDOWN_MINUTES_BETWEEN_CALLS: str
    SYNC_INTERVAL_SECONDS: Optional[str] = "60"
    BOT_ACTIVE: Optional[str] = "False"
    FIELD_TIKTOK_STATUS: Optional[str] = None
    VALUE_TIKTOK_STATUS_M0: Optional[str] = None
    FIELD_TIKTOK_REGION: Optional[str] = None
    FIELD_TIKTOK_CALLBACK_TIME: Optional[str] = None
    FIELD_TIKTOK_ASSIGNED_USER: Optional[str] = None
    FIELD_TIKTOK_RECIPIENT_USER: Optional[str] = None
    FIELD_TIKTOK_ASSIGNED_TIME: Optional[str] = None
    FIELD_TVV_USER: Optional[str] = None
    FIELD_TVV_ACTIVE: Optional[str] = None
    FIELD_TVV_REGION: Optional[str] = None
    FIELD_TVV_ROLE: Optional[str] = None

def verify_token(x_webhook_token: str = Header(default=None)):
    """Optional token verification for security."""
    if WEBHOOK_TOKEN and x_webhook_token != WEBHOOK_TOKEN:
        logger.warning(f"Unauthorized access attempt with token: {x_webhook_token}")
        raise HTTPException(status_code=401, detail="Unauthorized")

def process_m0_assignment(record_id: str):
    """Background task to process the assignment without blocking HTTP response."""
    try:
        config.validate_config()
        result = assign_m0_lead_to_tvv(lark_client, record_id)
        if result:
            logger.info(f"Background task: Lead {record_id} successfully assigned to TVV {result['name']}.")
        else:
            logger.warning(f"Background task: Lead {record_id} could not be assigned to any TVV.")
    except Exception as e:
        logger.error(f"Background task: Error assigning lead {record_id}: {e}")

def run_m0_sync_process():
    """Scan TikTok table for M0 leads and assign any that are unassigned."""
    logger.info("Scanning for unassigned M0 leads to sync...")
    try:
        config.validate_config()
        
        # Server-side filter: only filter by M0 status.
        # Note: checking Person field emptiness (CurrentValue.[field]="") does NOT work
        # reliably in Lark Bitable formulas, so we only filter by status server-side
        # and check "Người nhận data" emptiness client-side.
        filter_formula = f'CurrentValue.[{config.FIELD_TIKTOK_STATUS}]="{config.VALUE_TIKTOK_STATUS_M0}"'
        records = lark_client.list_records(config.TABLE_TIKTOK_ID, filter_formula=filter_formula)
        
        # Client-side validation: find M0 leads where either field is empty
        unassigned_records = []
        for rec in records:
            fields = rec.get("fields", {})
            status = fields.get(config.FIELD_TIKTOK_STATUS)
            if status == config.VALUE_TIKTOK_STATUS_M0:
                recipient_user = fields.get(config.FIELD_TIKTOK_RECIPIENT_USER)
                assigned_user = fields.get(config.FIELD_TIKTOK_ASSIGNED_USER)
                recipient_empty = _is_field_empty(recipient_user)
                assigned_empty = _is_field_empty(assigned_user)
                logger.debug(
                    f"Lead {rec.get('record_id')}: "
                    f"recipient_raw={recipient_user!r} (empty={recipient_empty}), "
                    f"assigned_raw={assigned_user!r} (empty={assigned_empty})"
                )
                if recipient_empty or assigned_empty:
                    unassigned_records.append(rec)
                    
        unassigned_m0_count = 0
        if unassigned_records:
            logger.info(f"Sync: Found {len(unassigned_records)} unassigned M0 leads. Distributing in batch...")
            results = assign_m0_leads_batch(lark_client, unassigned_records)
            unassigned_m0_count = len(results)
            logger.info(f"Sync: Successfully assigned {unassigned_m0_count} out of {len(unassigned_records)} leads.")
        else:
            logger.info("Sync: No unassigned M0 leads found.")
            
        return unassigned_m0_count
    except Exception as e:
        logger.error(f"Error during M0 sync scan: {e}")
        raise e

async def background_sync_loop():
    """Loop running indefinitely, syncing unassigned M0 leads at a configurable interval."""
    await asyncio.sleep(5)
    logger.info("Real-time background sync loop started.")
    while True:
        try:
            if config.BOT_ACTIVE:
                try:
                    config.validate_config()
                    run_m0_sync_process()
                except ValueError:
                    # Configuration is not complete yet, skip
                    pass
            else:
                # Standby state
                pass
        except Exception as e:
            logger.error(f"Error in background sync loop: {e}")
        
        # Responsive sleep checking config.SYNC_INTERVAL_SECONDS every second
        slept = 0
        interval = max(5, config.SYNC_INTERVAL_SECONDS)
        while slept < interval:
            await asyncio.sleep(1)
            slept += 1
            interval = max(5, config.SYNC_INTERVAL_SECONDS)

@app.on_event("startup")
def on_startup():
    asyncio.create_task(background_sync_loop())
    try:
        import webbrowser
        # Introduce a very slight delay to let the server start listening
        async def open_browser_later():
            await asyncio.sleep(1)
            webbrowser.open(f"http://localhost:{config.PORT}")
        asyncio.create_task(open_browser_later())
    except Exception as e:
        logger.warning(f"Could not automatically open browser: {e}")

@app.get("/")
def read_root():
    return FileResponse(get_resource_path("static/index.html"))

@app.get("/health")
def health_check():
    try:
        config.validate_config()
        lark_client.get_token()
        return {"status": "healthy", "lark_connection": "ok"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.post("/webhook/m0")
def webhook_m0(payload: M0WebhookPayload, background_tasks: BackgroundTasks, authorized: None = Depends(verify_token)):
    """
    Webhook endpoint triggered when a lead's status changes to M0.
    Expects JSON: {"record_id": "recXXXXXXXXX"}
    """
    record_id = payload.record_id
    if not record_id:
        raise HTTPException(status_code=400, detail="Missing record_id in payload")
        
    logger.info(f"Received webhook trigger for M0 Lead: {record_id}")
    background_tasks.add_task(process_m0_assignment, record_id)
    return {"status": "received", "record_id": record_id, "message": "Assignment task queued in background"}

@app.post("/cron/daily-t0")
def cron_daily_t0(authorized: None = Depends(verify_token)):
    """
    Endpoint to trigger the daily 8:00 AM T0 data distribution to TTS.
    [DISABLED] This feature has been disabled.
    """
    logger.info("Daily T0 distribution is disabled.")
    return {"status": "disabled", "message": "Daily T0 distribution to TTS is disabled"}

@app.get("/api/config")
def get_config():
    from config import get_current_env_values
    return get_current_env_values()

@app.post("/api/config")
def post_config(payload: ConfigPayload):
    from config import update_env_values
    try:
        update_env_values(payload.model_dump(exclude_none=True))
        return {"status": "success", "message": "Config updated and reloaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
def get_logs():
    return list(log_queue)

@app.post("/api/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(run_m0_sync_process)
        return {"status": "triggered", "message": "M0 synchronization task started in the background"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    if getattr(sys, 'frozen', False):
        uvicorn.run(app, host="0.0.0.0", port=config.PORT)
    else:
        uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=True)
