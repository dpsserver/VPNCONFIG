from playwright.sync_api import sync_playwright, TimeoutError
import os, time, subprocess, requests
from pathlib import Path




# ========== CONFIG ==========
EMAIL = "workoffice008@gmail.com"
PASSWORD = "_JriN9NBvx8sadA"

BOT_TOKEN = "8451321834:AAESbSun4JrPTkWsACW35au_dmcqW2QJC9U"
LOG_CHAT_ID = "-1003289273170"

HEADLESS = True
WAIT_BEFORE_DOWNLOAD = 3

BASE_DIR = "/workspaces/Localboy" # PYTHON SCRIPT RUN LOCATION .PY PATH RUN
VPN_DIR = f"{BASE_DIR}/vpnconfig"
WG_CONF = f"{VPN_DIR}/wg0.conf"


os.makedirs(VPN_DIR, exist_ok=True)

SERVERS = [
    "CA-FREE#7",
    "CA-FREE#8",
    "CA-FREE#13"
]

# ========== TELEGRAM ==========
def tg_log(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": LOG_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML"
            },
            timeout=10
        )
    except:
        pass

# ========== MAIN ==========
def run(playwright):
    browser = playwright.chromium.launch(headless=HEADLESS)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    try:
        tg_log("🚀 <b>VPN Auto Job Started (00:02)</b>")

        # LOGIN
        page.goto("https://account.protonvpn.com/login", timeout=60000)
        page.wait_for_selector("input", timeout=20000)
        page.get_by_test_id("input-input-element").fill(EMAIL)
        page.get_by_role("button", name="Continue").click()

        page.wait_for_selector("input[type='password']", timeout=20000)
        page.get_by_test_id("input-input-element").fill(PASSWORD)
        page.get_by_role("button", name="Sign in").click()

        page.wait_for_url("**/dashboard**", timeout=30000)

        # DOWNLOADS → WIREGUARD
        page.get_by_role("link", name="Downloads").click()
        page.wait_for_selector("text=WireGuard", timeout=30000)
        page.click("text=WireGuard")

        success = False
        downloaded_configs = []

        for server in SERVERS:
            try:
                tg_log(f"▶️ Trying <b>{server}</b>")

                page.wait_for_selector(
                    f"tr:has(td:has-text('{server}')) button:has-text('Create')",
                    timeout=20000
                )
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
                # Create unique filename for each server
                server_conf = f"{VPN_DIR}/wg0-{server.replace('#', '')}.conf"
                download.save_as(server_conf)
                downloaded_configs.append(server_conf)

                tg_log(f"✅ <b>{server}</b> config downloaded")
                success = True
                # Continue to next server instead of breaking

            except TimeoutError:
                tg_log(f"⚠️ <b>{server}</b> failed, trying next")
                continue

        if not success:
            tg_log("❌ <b>All servers failed – VPN NOT connected</b>")
            return

    finally:
        context.close()
        browser.close()

    # ========== WG-UP ==========
    try:
        # Use the first downloaded config
        if downloaded_configs:
            config_to_use = downloaded_configs[0]
            # Copy config to /etc/wireguard/ with sudo
            subprocess.run(["sudo", "mkdir", "-p", "/etc/wireguard"], check=True)
            subprocess.run(["sudo", "cp", config_to_use, "/etc/wireguard/wg0.conf"], check=True)
            
            subprocess.run(["sudo", "wg-quick", "up", "wg0"], check=True)
            tg_log(f"🔌 <b>wg-quick up SUCCESS</b> (using {os.path.basename(config_to_use)})")
        else:
            tg_log("❌ <b>No configs available for wg-quick</b>")
    except Exception as e:
        tg_log(f"❌ <b>wg-quick up FAILED</b>\n{e}")

# ========== RUN ==========
with sync_playwright() as playwright:
    run(playwright)
