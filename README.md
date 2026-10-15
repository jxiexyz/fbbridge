# FBBridge (Muse to Facebook Reels Bridge)

Decoupled bridge and webhook service to automatically receive AI-rendered videos from external agents (such as Muse) and publish them directly to Facebook Page Reels via the official Graph API.

## Problem Solved

Connecting Facebook accounts directly to cloud AI generation tools (like Muse) often triggers region-bans or geo-restrictions on video rendering due to location/locale mismatch. 

**FBBridge** completely decouples rendering from publishing:
1. **Muse (Producer):** Renders the video in its isolated cloud environment and pushes the binary via a lightweight cURL webhook. Muse never interacts with Facebook.
2. **FBBridge (Consumer):** Receives the binary payload over HTTPS, verifies the format, queues it for background upload to Facebook Reels, and immediately wipes local copies to prevent disk saturation.

---

## Architecture

```
[Muse AI Agent (Cron)]
   │
   ▼ (1. Render video: ~/workspace/output.mp4)
   ▼ (2. cURL POST binary + caption)
[HTTPS Webhook: https://momoai.fun/upload]
   │
   ▼ (3. Reverse proxy Nginx)
[FBBridge FastAPI (127.0.0.1:8080)]
   │
   ├─► (4. Fast HTTP 200 response -> Muse deletes local file)
   │
   └─► [Background Worker]
         ├─► (5. Start Reels Phase -> Ruploadd API)
         ├─► (6. Binary Stream Transfer)
         ├─► (7. Publish Reel with original caption)
         └─► (8. Auto-delete local temp MP4 file)
```

---

## Installation & Setup

### 1. Requirements

- Python 3.10+
- Dependencies:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Configuration (`fb_config.json`)

Create `fb_config.json` in the root folder or set `FB_CONFIG_PATH`:

```json
{
  "page_id": "YOUR_FB_PAGE_ID",
  "page_name": "Your Page Name",
  "page_token": "YOUR_PERMANENT_PAGE_ACCESS_TOKEN"
}
```

#### Generating a Never-Expiring Token:
Run the built-in exchange helper:
```bash
python3 exchange_token.py <APP_ID> <APP_SECRET> <SHORT_USER_TOKEN> <PAGE_ID>
```

### 3. Running with PM2

```bash
pm2 start "python3 -m uvicorn main:app --host 127.0.0.1 --port 8080" --name muse-receiver
pm2 save
```

### 4. Nginx Reverse Proxy Config

Ensure your Nginx configuration allows large video uploads:

```nginx
server {
    server_name yourdomain.com;
    client_max_body_size 100M;
    proxy_read_timeout 300;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 5. Automated Disk Sweeper (Fail-Safe)

Add a safety-net cron rule to purge any stuck MP4 files older than 15 minutes:

```bash
*/30 * * * * find /home/ubuntu/muse_uploads -type f -name "*.mp4" -mmin +15 -delete
```

---

## Muse Agent Integration

Add this step to your Muse cron pipeline after video rendering completes:

```bash
curl -X POST https://yourdomain.com/upload \
  -F "video=@$VIDEO_PATH" \
  -F "caption=Your dynamic video description #reels"

# If curl returns "status":"success", remove the local file
rm -f "$VIDEO_PATH"
```
