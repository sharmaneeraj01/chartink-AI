import time
from collections import Counter
import pandas as pd
from playwright.sync_api import sync_playwright
import os
import requests
from tabulate import tabulate

# ==========================================
# CONFIG
# ==========================================
DASHBOARD_URL = "https://chartink.com/dashboard/334725"
SCREENER_URL = "https://chartink.com/screener/2-week-inside-bar-2026"
HEADLESS = True


# ==========================================
# TELEGRAM
# ==========================================
def send_to_telegram(message):
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")

    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Missing Telegram credentials")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    response = requests.post(url, data=payload)
    print("Telegram response:", response.text)


# ==========================================
# DASHBOARD SCRAPER
# ==========================================
def scrape_dashboard(page):
    widget_results = []

    print("Opening dashboard...")
    page.goto(DASHBOARD_URL)

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)

    page.mouse.wheel(0, 5000)
    page.wait_for_timeout(3000)

    tables = page.query_selector_all("table")
    print(f"Tables found: {len(tables)}")

    for i, table in enumerate(tables):
        stocks = table.query_selector_all("a")

        symbols = []
        for s in stocks:
            text = s.inner_text().strip()

            if text.isupper() and 2 <= len(text) <= 15:
                symbols.append(text)

        symbols = list(set(symbols))

        if len(symbols) >= 5:
            print(f"Widget {i+1}: {len(symbols)} stocks")
            widget_results.append(symbols)

    print(f"Total widgets captured: {len(widget_results)}")
    return widget_results


# ==========================================
# SCREENER SCRAPER
# ==========================================
def scrape_screener(page):
    results = []

    print("Running screener...")
    page.goto(SCREENER_URL)

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)

    rows = page.query_selector_all("table tbody tr")
    print(f"Screener rows: {len(rows)}")

    for row in rows:
        cols = row.query_selector_all("td")

        if len(cols) < 6:
            continue

        symbol = cols[2].inner_text().strip()
        price = cols[3].inner_text().strip()
        change = cols[4].inner_text().strip()

        volume_text = cols[5].inner_text().strip()
        volume = int(volume_text.replace(",", "")) if volume_text else 0

        results.append([symbol, price, change, volume])

    # 🔥 SORT BY VOLUME
    results = sorted(results, key=lambda x: x[3], reverse=True)

    # ✅ LIMIT TO TOP 100 STOCKS
    MAX_STOCKS = 60
    results = results[:MAX_STOCKS]

    return results


# ==========================================
# RANKING
# ==========================================
def rank_stocks(widget_lists):
    counter = Counter()
    for lst in widget_lists:
        counter.update(lst)
    return counter.most_common()


# ==========================================
# MAIN
# ==========================================
def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()

        # Dashboard
        widget_lists = scrape_dashboard(page)

        if not widget_lists:
            msg = "❌ No dashboard data."
            print(msg)
            send_to_telegram(msg)
            return

        ranked = rank_stocks(widget_lists)

        # Screener
        screener_results = scrape_screener(page)

        browser.close()

    # =========================
    # FORMAT DASHBOARD
    # =========================
    ranked = [r for r in ranked if r[1] >= 2]
    # ✅ LIMIT TO TOP 100 STOCKS
    MAX_STOCKS = 25
    ranked = ranked[:MAX_STOCKS]

    if ranked:
        df = pd.DataFrame(ranked, columns=["Stock", "Count"])
        df["Strength"] = df["Count"].apply(lambda x: "🔥 Strong" if x >= 3 else "⚡ Medium")
        dashboard_table = tabulate(df, headers="keys", tablefmt="github", showindex=False)
    else:
        dashboard_table = "No strong signals."

    # =========================
    # FORMAT SCREENER
    # =========================
    if screener_results:
        screener_table = tabulate(
            screener_results,
            headers=["Stock", "Price", "%Change", "Volume"],
            tablefmt="github"
        )
    else:
        screener_table = "No screener results."

    # =========================
    # FINAL MESSAGE (SAFE FORMAT)
    # =========================
    message = (
        "📊 *Stocks for the Day *\n\n"
        "🔹 Dashboard Signals\n"
        "```\n"
        f"{dashboard_table}\n"
        "```\n\n"
        "🔹 2 WEEK Inside bar Screener\n"
        "```\n"
        f"{screener_table}\n"
        "```"
    )

    print(message)
    send_to_telegram(message)


if __name__ == "__main__":
    run()
