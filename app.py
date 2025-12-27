from playwright.sync_api import sync_playwright, TimeoutError
import os, zipfile, json, hashlib
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# ================= CONFIG =================
EMAIL = os.getenv("PROTON_EMAIL")
PASSWORD = os.getenv("PROTON_PASSWORD")

if not EMAIL or not PASSWORD:
    raise RuntimeError("❌ Missing PROTON_EMAIL / PROTON_PASSWORD")

# Google Drive Service Account JSON (SECRET)
SA_JSON = os.getenv("GDRIVE_SA_JSON")
if not SA_JSON:
    raise RuntimeError("❌ Missing GDRIVE_SA_JSON secret")

HEADLESS = True
WAIT_BEFORE_DOWNLOAD = 3

SERVERS = [
    "CA-FREE#7",
    "CA-FREE#8",
    "CA-FREE#13"
]

DRIVE_FOLDER_NAME = "ProtonVPN-WireGuard"
ZIP_NAME = "wireguard_configs.zip"

BASE_DIR = Path.cwd()
VPN_DIR = BASE_DIR / "vpnconfig"
ZIP_FILE = BASE_DIR / ZIP_NAME
STATE_FILE = BASE_DIR / "state.json"

VPN_DIR.mkdir(exist_ok=True)

# ================= UTIL =================
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# ================= GOOGLE DRIVE (SERVICE ACCOUNT) =================
def get_drive_service():
    creds_dict = json.loads(SA_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def get_or_create_folder(service, name):
    q = (
        f"name='{name}' and "
        "mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id)").execute()
    if res["files"]:
        return res["files"][0]["id"]

    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]

def delete_old_zip(service, folder_id):
    q = f"name='{ZIP_NAME}' and '{folder_id}' in parents and trashed=false"
    res = service.files().list(q=q, fields="files(id)").execute()
    for f in res["files"]:
        service.files().delete(fileId=f["id"]).execute()

def upload_zip(service, folder_id, zip_path):
    meta = {"name": ZIP_NAME, "parents": [folder_id]}
    media = MediaFileUpload(zip_path, mimetype="application/zip")
    f = service.files().create(
        body=meta,
        media_body=media,
        fields="id"
    ).execute()
    return f["id"]

# ================= MAIN =================
def run(playwright):
    browser = playwright.chromium.launch(headless=HEADLESS)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    downloaded = []

    try:
        # LOGIN
        page.goto("https://account.protonvpn.com/login", timeout=60000)
        page.get_by_test_id("input-input-element").fill(EMAIL)
        page.get_by_role("button", name="Continue").click()

        page.wait_for_selector("input[type='password']", timeout=20000)
        page.get_by_test_id("input-input-element").fill(PASSWORD)
        page.get_by_role("button", name="Sign in").click()

        page.wait_for_url("**/dashboard**", timeout=30000)

        # DOWNLOADS
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

            except TimeoutError:
                continue

    finally:
        context.close()
        browser.close()

    if not downloaded:
        print("❌ No configs downloaded")
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
        print("♻️ ZIP unchanged – skipping upload")
        return

    # DRIVE UPLOAD
    service = get_drive_service()
    folder_id = get_or_create_folder(service, DRIVE_FOLDER_NAME)
    delete_old_zip(service, folder_id)
    file_id = upload_zip(service, folder_id, ZIP_FILE)

    STATE_FILE.write_text(json.dumps({
        "zip_hash": zip_hash,
        "file_id": file_id
    }))

    print("✅ Uploaded new ZIP to Google Drive:", file_id)

# ================= RUN =================
with sync_playwright() as playwright:
    run(playwright)
