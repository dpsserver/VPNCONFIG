from playwright.sync_api import sync_playwright, TimeoutError
import os, time, requests, zipfile, json
from pathlib import Path

# ================= ENV =================
EMAIL = os.getenv("PROTON_EMAIL")
PASSWORD = os.getenv("PROTON_PASSWORD")
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_CHAT_ID = os.getenv("LOG_CHAT_ID")
ZIP_CHAT_ID = os.getenv("ZIP_CHAT_ID")

if not all([EMAIL, PASSWORD, BOT_TOKEN, LOG_CHAT_ID, ZIP_CHAT_ID]):
    raise RuntimeError("❌ Missing required environment variables")

HEADLESS = True
WAIT_BEFORE_DOWNLOAD = 3

BASE_DIR = Path.cwd()
VPN_DIR = BASE_DIR / "vpnconfig"
ZIP_FILE = BASE_DIR / "wireguard_configs.zip"
STATE_FILE = BASE_DIR / "last_file_id.json"

VPN_DIR.mkdir(exist_ok=True)

SERVERS = [
    "CA-FREE#7",
    "CA-FREE#8",
    "CA-FREE#13"
]

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ================= TELEGRAM =================
def tg_send(chat_id, text):
    requests.post(
        f"{TG_API}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15
    )

def tg_send_file_and_get_id(chat_id, path, caption):
    with open(path, "rb") as f:
        r = requests.post(
            f"{TG_API}/sendDocument",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"document": f},
            timeout=60
        )

    r.raise_for_status()
    file_id = r.json()["result"]["document"]["file_id"]
    return file_id

def tg_send_by_file_id(chat_id, file_id, caption):
    requests.post(
        f"{TG_API}/sendDocument",
        data={
            "chat_id": chat_id,
,
            "document": file_id,
            "caption": caption,
            "parse_mode": "HTML"
        },
        timeout=15
    )

# ================= MAIN =================
def run(playwright):
    tg_send(LOG_CHAT_ID, "🚀 <b>ProtonVPN WireGuard ZIP Job Started</b>")

    browser = playwright.chromium.launch(headless=HEADLESS)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    downloaded = []

    try:
        page.goto("https://account.protonvpn.com/login", timeout=60000)
        page.get_by_test_id("input-input-element").fill(EMAIL)
        page.get_by_role("button", name="Continue").click()

        page.wait_for_selector("input[type='password']", timeout=20000)
        page.get_by_test_id("input-input-element").fill(PASSWORD)
        page.get_by_role("button", name="Sign in").click()

        page.wait_for_url("**/dashboard**", timeout=30000)

        page.get_by_role("link", name="Downloads").click()
        page.wait_for_selector("text=WireGuard", timeout=30000)
        page.click("text=WireGuard")

        for server in SERVERS:
            try:
                tg_send(LOG_CHAT_ID, f"▶️ Downloading <b>{server}</b>")

                page.locator(
                    f"tr:has(td:has-text('{server}')) button:has-text('Create')"
                ).click()

                page.wait_for_selector(".modal-two-footer", timeout=20000)
                page.wait_for_timeout(WAIT_BEFORE_DOWNLOAD * 1000)

                with page.expect_download(timeout=30000) as d:
                    page.locator(".modal-two-footer button:has-text('Download')").click()

                download = d.value
                fname = VPN_DIR / f"wg-{server.replace('#','')}.conf"
                download.save_as(fname)
                downloaded.append(fname)

                tg_send(LOG_CHAT_ID, f"✅ <b>{server}</b> downloaded")

            except TimeoutError:
                tg_send(LOG_CHAT_ID, f"⚠️ <b>{server}</b> failed")
                continue

    finally:
        context.close()
        browser.close()

    if not downloaded:
        tg_send(LOG_CHAT_ID, "❌ No configs downloaded")
        return

    # ================= ZIP =================
    with zipfile.ZipFile(ZIP_FILE, "w", zipfile.ZIP_DEFLATED) as z:
        for f in downloaded:
            z.write(f, f.name)

    tg_send(LOG_CHAT_ID, "📦 ZIP created")

    # ================= UPLOAD + FILE_ID =================
    file_id = tg_send_file_and_get_id(
        ZIP_CHAT_ID,
        ZIP_FILE,
        "📦 <b>WireGuard Configs ZIP</b>\n3 servers included"
    )

    with open(STATE_FILE, "w") as f:
        json.dump({"file_id": file_id}, f)

    tg_send(LOG_CHAT_ID, f"🧾 <b>File ID saved</b>\n<code>{file_id}</code>")

    # ================= REPOST USING FILE_ID =================
    tg_send_by_file_id(
        ZIP_CHAT_ID,
        file_id,
        "♻️ <b>Re-posted WireGuard ZIP</b>\n(no re-upload, file_id reuse)"
    )

    tg_send(LOG_CHAT_ID, "✅ ZIP reposted successfully")

# ================= RUN =================
with sync_playwright() as playwright:
    run(playwright)
