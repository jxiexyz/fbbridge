import os
import json
import shutil
import logging
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fbbridge")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.getenv("FB_CONFIG_PATH", os.path.join(BASE_DIR, "fb_config.json"))
if not os.path.exists(CONFIG_PATH):
    home_cfg = os.path.expanduser("~/fb_config.json")
    if os.path.exists(home_cfg):
        CONFIG_PATH = home_cfg

UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.expanduser("~/muse_uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Muse to Facebook Reels Bridge")

def load_fb_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {
        "page_id": os.getenv("FB_PAGE_ID", ""),
        "page_token": os.getenv("FB_PAGE_TOKEN", ""),
        "page_name": os.getenv("FB_PAGE_NAME", "Default Page"),
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "telegram_thread_id": os.getenv("TELEGRAM_THREAD_ID", "")
    }

def send_telegram_notification(text: str):
    config = load_fb_config()
    bot_token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")
    thread_id = config.get("telegram_thread_id")

    if not bot_token or not chat_id:
        return

    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        if thread_id:
            payload["message_thread_id"] = int(thread_id)

        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=payload,
            timeout=15
        ).json()
        logger.info(f"Telegram notification sent: {r.get('ok')}")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

def upload_fb_reel_worker(file_path: str, caption: str):
    config = load_fb_config()
    page_id = config.get("page_id")
    token = config.get("page_token")
    page_name = config.get("page_name", "Wintermute Cozy Style")

    if not page_id or not token:
        logger.error("FB config missing page_id or page_token. Cannot upload.")
        send_telegram_notification(f"<b>❌ Gagal Upload:</b> Konfigurasi Facebook (Page ID / Token) belum diset.")
        return

    file_size = os.path.getsize(file_path)
    size_mb = file_size / (1024 * 1024)
    logger.info(f"Uploading Reel to FB ({page_id}): {file_path} ({file_size} bytes)")

    try:
        # Phase 1: Initialize Reel
        r1 = requests.post(
            f"https://graph.facebook.com/v19.0/{page_id}/video_reels",
            params={"access_token": token, "upload_phase": "start"},
            timeout=30
        ).json()

        if "video_id" not in r1:
            logger.error(f"FB Reels start phase failed: {r1}")
            send_telegram_notification(f"<b>❌ Gagal Inisiasi Reels:</b> <code>{r1}</code>")
            return

        video_id = r1["video_id"]
        upload_url = r1["upload_url"]

        # Phase 2: Binary Video Transfer
        with open(file_path, "rb") as f:
            r2 = requests.post(
                upload_url,
                headers={
                    "Authorization": f"OAuth {token}",
                    "offset": "0",
                    "file_size": str(file_size)
                },
                data=f,
                timeout=300
            ).json()

        if not r2.get("success"):
            logger.error(f"FB Reels binary transfer failed: {r2}")
            send_telegram_notification(f"<b>❌ Gagal Transfer Binary Reels:</b> <code>{r2}</code>")
            return

        # Phase 3: Publish Reel
        r3 = requests.post(
            f"https://graph.facebook.com/v19.0/{page_id}/video_reels",
            params={
                "access_token": token,
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": caption
            },
            timeout=30
        ).json()

        logger.info(f"FB Reels publish result: {r3}")

        if r3.get("success"):
            reel_url = f"https://www.facebook.com/reel/{video_id}"
            report_msg = (
                f"<b>✅ Video Reels Berhasil Di-publish!</b>\n\n"
                f"🎬 <b>Halaman:</b> {page_name}\n"
                f"🆔 <b>Video ID:</b> <code>{video_id}</code>\n"
                f"🔗 <b>Link:</b> <a href=\"{reel_url}\">{reel_url}</a>\n"
                f"📦 <b>Ukuran:</b> {size_mb:.2f} MB\n\n"
                f"📝 <b>Caption:</b>\n"
                f"<blockquote>{caption}</blockquote>"
            )
            send_telegram_notification(report_msg)
        else:
            send_telegram_notification(f"<b>❌ Gagal Publish Reels:</b> <code>{r3}</code>")

    except Exception as e:
        logger.error(f"Exception during FB Reels upload: {e}")
        send_telegram_notification(f"<b>❌ Exception saat upload:</b> <code>{str(e)}</code>")
    finally:
        # ponytail: immediate delete after upload attempt to prevent VPS disk saturation
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Local file cleaned up: {file_path}")

@app.get("/")
def health():
    config = load_fb_config()
    return {
        "status": "online",
        "service": "muse-fb-bridge",
        "target_page": config.get("page_name", "unknown")
    }

@app.post("/upload")
async def receive_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    caption: str = Form(""),
):
    filename = video.filename or "video.mp4"
    if not filename.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
        raise HTTPException(status_code=400, detail="Invalid video format")

    dest_path = os.path.join(UPLOAD_DIR, filename)
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        file_size = os.path.getsize(dest_path)
        logger.info(f"Video received from Muse: {dest_path} ({file_size} bytes)")

        # Dispatch upload task in background for non-blocking HTTP response
        background_tasks.add_task(upload_fb_reel_worker, dest_path, caption)

        return JSONResponse({
            "status": "success",
            "message": "Video accepted and queued for FB Reels upload",
            "filename": video.filename,
            "bytes": file_size
        })
    except Exception as e:
        logger.error(f"Error handling video upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))
