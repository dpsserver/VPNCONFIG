from playwright.sync_api import sync_playwright, TimeoutError
import os, zipfile, json, hashlib
from pathlib import Path
import boto3
import requests

# ================= ENV =================
PROTON_EMAIL = os.getenv("PROTON_EMAIL")
PROTON_PASSWORD = os.getenv("PROTON_PASSWORD")

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

# Telegram (FROM SECRETS)
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

if not all([
    PROTON_EMAIL,
    PROTON_PASSWORD,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    BOT_TOKEN,
    LOG_CHANNEL_ID
]):
    raise RuntimeError("❌ Missing required environment variables")

# ================= CONFIG =================
HEADLESS = True
WAIT_BEFORE_DOWNLOAD = 3

BUCKET_NAME = "protonvpn-wireguard-auto"
S3_PREFIX = "wireguard/"
S3_KEY = f"{S3_PREFIX}wireguard_configs.zip"

SERVERS = [
    "CA-FREE#7",
    "CA-FREE#8",
    "CA-FREE#13"
]

BASE_DIR = Path.cwd()
VPN_DIR = BASE_DIR / "vpnconfig"
ZIP_FILE = BASE_DIR / "wireguard_configs.zip"
STATE_FILE = BASE_DIR / "state.json"

VPN_DIR.mkdir(exist_ok=True)

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ================= UTIL =================
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def tg_send(text):
    requests.post(
        f"{TG_API}/sendMessage",
        data={
            "chat_id": LOG_CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=20
    )

# ================= S3 =================
def s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )

def delete_old_zips():
    s3 = s3_client()
    resp = s3.list_objects_v2(
        Bucket=BUCKET_NAME,
        Prefix=S3_PREFIX
    )

    if "Contents" not in resp:
        return

    for obj in resp["Contents"]:
        key = obj["Key"]
        if key.endswith(".zip"):
            s3.delete_object(Bucket=BUCKET_NAME, Key=key)

def upload_to_s3(path: Path):
    s3 = s3_client()
    s3.upload_file(
        Filename=str(path),
        Bucket=BUCKET_NAME,
        Key=S3_KEY
    )

def presigned_url(expire_seconds=86400):
    s3 = s3_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": BUCKET_NAME,
            "Key": S3_KEY
        },
        ExpiresIn=expire_seconds
    )

# ================= MAIN =================
def run(playwright):
    tg_send("🚀 <b>ProtonVPN WireGuard S3 Job Started</b>")

    browser = playwright.chromium.launch(headless=HEADLESS)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    downloaded = []

    try:
        # LOGIN
        page.goto("https://account.protonvpn.com/login", timeout=60000)
        page.get_by_test_id("input-input-element").fill(PROTON_EMAIL)
        page.get_by_role("button", name="Continue").click()

        page.wait_for_selector("input[type='password']", timeout=20000)
        page.get_by_test_id("input-input-element").fill(PROTON_PASSWORD)
        page.get_by_role("button", name="Sign in").click()

        page.wait_for_url("**/dashboard**", timeout=30000)

        # DOWNLOAD WIREGUARD
        page.get_by_role("link", name="Downloads").click()
        page.wait_for_selector("text=WireGuard", timeout=30000)
        page.click("text=WireGuard")

        for server in SERVERS:
            try:
                page.locator(
                    f"tr:has(td:has-text('{server}')) button:has-text('Create')"
                ).click()

                page.wait_for_selector(".modal-two-footer", timeout=20000)
                page.wait_for_timeout(WAIT_BEFORE_DOWNLOAD * 1000)

                with page.expect_download(timeout=30000) as d:
                    page.locator(
                        ".modal-two-footer button:has-text('Download')"
                    ).click()

                download = d.value
                fname = VPN_DIR / f"wg-{server.replace('#','')}.conf"
                download.save_as(fname)
                downloaded.append(fname)

                tg_send(f"✅ <b>{server}</b> downloaded")

            except TimeoutError:
                tg_send(f"⚠️ <b>{server}</b> failed")
                continue

    finally:
        context.close()
        browser.close()

    if not downloaded:
        tg_send("❌ <b>No configs downloaded</b>")
        return

    # ZIP
    with zipfile.ZipFile(ZIP_FILE, "w", zipfile.ZIP_DEFLATED) as z:
        for f in downloaded:
            z.write(f, f.name)

    zip_hash = sha256(ZIP_FILE)

    # STATE CHECK
    state = {}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())

    if state.get("zip_hash") == zip_hash:
        tg_send("♻️ <b>ZIP unchanged – skipping upload</b>")
        return

    # S3 UPLOAD
    delete_old_zips()
    upload_to_s3(ZIP_FILE)
    url = presigned_url()

    STATE_FILE.write_text(json.dumps({"zip_hash": zip_hash}))

    tg_send(
        "📦 <b>New WireGuard ZIP Uploaded</b>\n\n"
        f"🔗 <a href='{url}'>Download (valid 24h)</a>"
    )

# ================= RUN =================
with sync_playwright() as playwright:
    run(playwright)
