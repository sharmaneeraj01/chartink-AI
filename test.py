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

    for table in tables:
        stocks = table.query_selector_all("a")

        symbols = []
        for s in stocks:
            text = s.inner_text().strip()
            if text.isupper() and 2 <= len(text) <= 15:
                symbols.append(text)

        symbols = list(set(symbols))

        if len(symbols) >= 5:
            widget_results.append(symbols)

    return widget_results


# ==========================================
# SCREENER SCRAPER (ONLY FOR TAGGING)
# ==========================================
def scrape_screener(page):
    results = []

    print("Running screener...")
    page.goto(SCREENER_URL)

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)

    rows = page.query_selector_all("table tbody tr")

    for row in rows:
        cols = row.query_selector_all("td")

        if len(cols) < 6:
            continue

        symbol = cols[2].inner_text().strip()
        results.append(symbol)

    return set(results)  # only symbols needed


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

        widget_lists = scrape_dashboard(page)

        if not widget_lists:
            send_to_telegram("❌ No dashboard data.")
            return

        ranked = rank_stocks(widget_lists)

        # Screener only for tagging
        screener_set = scrape_screener(page)

        browser.close()

    # =========================
    # FILTER DASHBOARD
    # =========================
    ranked = [r for r in ranked if r[1] >= 2][:30]

    # =========================
    # PURE SCORING (NO SCREENER)
    # =========================
    combined = []

    for stock, count in ranked:
        score = count * 10   # clean scoring

        tag = "IB" if stock in screener_set else ""

        combined.append((stock, count, score, tag))

    # SORT
    combined = sorted(combined, key=lambda x: x[2], reverse=True)

    # =========================
    # TOP PICKS
    # =========================
    top_picks = combined[:15]

    top_text = "\n".join([
        f"{i+1}. {s[0]} | Score:{s[2]} {s[3]}"
        for i, s in enumerate(top_picks)
    ]) if top_picks else "No strong picks."

    # =========================
    # DASHBOARD TABLE
    # =========================
    df = pd.DataFrame(ranked, columns=["Stock", "Count"])
    df["Strength"] = df["Count"].apply(lambda x: "🔥" if x >= 3 else "⚡")

    dashboard_table = tabulate(df, headers="keys", tablefmt="github", showindex=False)

    # =========================
    # FINAL MESSAGE
    # =========================
    message = (
        "📊 *Stocks for the Day*\n\n"

        "🔥 *Top Picks (Ranked)*\n"
        "```\n"
        f"{top_text}\n"
        "```\n\n"

        "🔹 Dashboard Signals\n"
        "```\n"
        f"{dashboard_table}\n"
        "```"
    )

    # TELEGRAM SAFE LIMIT
    if len(message) > 4000:
        message = message[:4000]

    print(message)
    send_to_telegram(message)


if __name__ == "__main__":
    run()
