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
HEADLESS = True

# ==========================================
# TELEGRAM FUNCTION
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
# SCRAPER ENGINE
# ==========================================
def scrape_chartink_dashboard(url):
    widget_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()

        print("Opening dashboard...")
        page.goto(url)

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)

        # Scroll to load all widgets
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

            # Filter weak widgets (optional but recommended)
            if len(symbols) >= 5:
                print(f"Widget {i+1}: {len(symbols)} stocks")
                widget_results.append(symbols)

        browser.close()

    print(f"\nTotal widgets captured: {len(widget_results)}")

    return widget_results


# ==========================================
# INTERSECTION ENGINE
# ==========================================
def get_common_stocks(widget_lists, min_count=2):
    counter = Counter()

    for lst in widget_lists:
        counter.update(lst)

    return [stock for stock, count in counter.items() if count >= min_count]


# ==========================================
# RANKING ENGINE
# ==========================================
def rank_stocks(widget_lists):
    counter = Counter()

    for lst in widget_lists:
        counter.update(lst)

    return counter.most_common()


# ==========================================
# OUTPUT ENGINE
# ==========================================
def save_results(common, ranked):
    ranked = [r for r in ranked if r[1] >= 2]

    print("\n📊 HIGH CONVICTION STOCKS (>=2 scanners)\n")

    if not ranked:
        msg = "❌ No strong signals today."
        print(msg)
        send_to_telegram(msg)
        return

    df = pd.DataFrame(ranked, columns=["Stock", "Scanner Count"])

    df["Strength"] = df["Scanner Count"].apply(
        lambda x: "🔥 Strong" if x >= 3 else "⚡ Medium"
    )

    df = df.sort_values(by="Scanner Count", ascending=False)

    table = tabulate(df, headers="keys", tablefmt="github", showindex=False)

    print(table)

    message = f"📊 *Chartink AI Signals*\n\n```\n{table}\n```"
    send_to_telegram(message)


# ==========================================
# MAIN PIPELINE
# ==========================================
def run():
    widget_lists = scrape_chartink_dashboard(DASHBOARD_URL)

    if not widget_lists:
        msg = "❌ No data extracted."
        print(msg)
        send_to_telegram(msg)
        return

    common = get_common_stocks(widget_lists)
    ranked = rank_stocks(widget_lists)

    save_results(common, ranked)


if __name__ == "__main__":
    run()
