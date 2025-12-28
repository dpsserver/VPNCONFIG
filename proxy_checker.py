import requests
import socks
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

# ================= CONFIG =================
FETCH_URLS = [
    "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/socks5.txt",
    "https://raw.githubusercontent.com/ClearProxy/checked-proxy-list/main/custom/discord/socks5.txt",
    "https://raw.githubusercontent.com/dpangestuw/Free-Proxy/main/socks5_proxies.txt",
    "https://raw.githubusercontent.com/gitrecon1455/ProxyScraper/main/proxies.txt",
    "https://raw.githubusercontent.com/vmheaven/VMHeaven-Free-Proxy-Updated/main/socks5.txt",
    "https://raw.githubusercontent.com/openproxyhub/proxy-exports/main/socks5.txt",
    "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt",
    "https://raw.githubusercontent.com/wiki/gfpcom/free-proxy-list/lists/socks5.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/master/socks5.txt",
]

TIMEOUT = 6
THREADS = 120
GEO_URL = "http://ip-api.com/json"

OUT_ALL = "socks5_all.txt"
OUT_ALIVE = "socks5_alive.txt"
OUT_DEAD = "socks5_dead.txt"
OUT_FULL = "socks5_alive_country.txt"

lock = threading.Lock()

# ================= FETCH =================
def fetch_proxies():
    proxies = set()

    for url in FETCH_URLS:
        try:
            print(f"📥 Fetching {url}")
            r = requests.get(url, timeout=10)
            for line in r.text.splitlines():
                line = line.strip()
                if ":" in line and line.count(":") == 1:
                    proxies.add(line)
        except Exception as e:
            print(f"❌ Fetch failed: {url} → {e}")

    with open(OUT_ALL, "w") as f:
        for p in sorted(proxies):
            f.write(p + "\n")

    print(f"\n✅ Total fetched: {len(proxies)}\n")
    return list(proxies)

# ================= CHECK =================
def check_proxy(proxy):
    ip, port = proxy.split(":")
    port = int(port)

    try:
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, ip, port)
        s.settimeout(TIMEOUT)
        s.connect(("ip-api.com", 80))

        proxies = {
            "http": f"socks5://{ip}:{port}",
            "https": f"socks5://{ip}:{port}",
        }

        r = requests.get(GEO_URL, proxies=proxies, timeout=TIMEOUT)
        data = r.json()

        if data.get("status") != "success":
            raise Exception("Geo fail")

        country = data.get("country", "Unknown")
        isp = data.get("isp", "Unknown")

        with lock:
            print(f"🟢 ALIVE {ip}:{port} | {country}")
            open(OUT_ALIVE, "a").write(f"{ip}:{port}\n")
            open(OUT_FULL, "a").write(f"{ip}:{port} | {country} | {isp}\n")

    except Exception:
        with lock:
            print(f"🔴 DEAD  {proxy}")
            open(OUT_DEAD, "a").write(proxy + "\n")

# ================= MAIN =================
def main():
    open(OUT_ALIVE, "w").close()
    open(OUT_DEAD, "w").close()
    open(OUT_FULL, "w").close()

    proxies = fetch_proxies()

    print("🚀 Checking proxies...\n")

    with ThreadPoolExecutor(max_workers=THREADS) as exe:
        exe.map(check_proxy, proxies)

    print("\n✅ DONE")
    print(f"Alive → {OUT_ALIVE}")
    print(f"Dead  → {OUT_DEAD}")
    print(f"Full  → {OUT_FULL}")

if __name__ == "__main__":
    main()
