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
SCREENER_URL = "https://chartink.com/screener/2-3-4-week-insidebar-2026"
EMA_SCREENER_URL = "https://chartink.com/screener/10-20-ema-reversal-stocks"
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
# GENERIC SCREENER SCRAPER
# ==========================================
def scrape_chartink_table(page, url):
    results = []

    print(f"Running screener: {url}")
    page.goto(url)

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)

    rows = page.query_selector_all("table tbody tr")

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
# SCREENER PRIORITY + PRICE SORT
# ==========================================
def prioritize_and_sort_screener(screener_results, top_symbols, limit):
    def safe_price(row):
        try:
            return float(row[1].replace(",", ""))
        except:
            return float('inf')

    # NO extra column here
    priority = [row for row in screener_results if row[0] in top_symbols]
    others = [row for row in screener_results if row[0] not in top_symbols]

    priority_sorted = sorted(priority, key=safe_price)
    others_sorted = sorted(others, key=safe_price)

    return (priority_sorted + others_sorted)[:limit]
    
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

        # Fetch BOTH screeners
        ib_results = scrape_chartink_table(page, SCREENER_URL)
        ema_results = scrape_chartink_table(page, EMA_SCREENER_URL)

        ib_set = {s[0] for s in ib_results}
        ema_set = {s[0] for s in ema_results}

        browser.close()

    # =========================
    # FILTER
    # =========================
    ranked = [r for r in ranked if r[1] >= 2]

    # =========================
    # SCORING
    # =========================
    combined = []

    for stock, count in ranked:
        score = count * 10

        tags = []
        if stock in ib_set:
            tags.append("IB")
        if stock in ema_set:
            tags.append("EMA")

        tag = "+".join(tags)

        combined.append((stock, count, score, tag))

    combined = sorted(combined, key=lambda x: x[2], reverse=True)

    # =========================
    # TOP PICKS
    # =========================
    top_picks = combined[:5]
    top_symbols = {s[0] for s in top_picks}

    top_text = "\n".join([
        f"{i+1}. {s[0]} | Score:{s[2]} {s[3]}"
        for i, s in enumerate(top_picks)
    ]) if top_picks else "No strong picks."

    # =========================
    # DASHBOARD TABLE
    # =========================
    remaining = [r for r in ranked if r[0] not in top_symbols][:30]

    df = pd.DataFrame(remaining, columns=["Stock", "Count"])
    df["Strength"] = df["Count"].apply(lambda x: "🔥" if x >= 3 else "⚡")

    dashboard_table = tabulate(df, headers="keys", tablefmt="github", showindex=False)

    # =========================
    # SCREENER TABLES (PRIORITIZED + SORTED)
    # =========================

    ib_final = prioritize_and_sort_screener(ib_results, top_symbols, 20)
    ema_final = prioritize_and_sort_screener(ema_results, top_symbols, 15)

    ib_table = tabulate(
    ib_final,
    headers=["Stock", "Price", "%Change", "Volume"],
    tablefmt="github"
    )
    
    ema_table = tabulate(
    ema_final,
    headers=["Stock", "Price", "%Change", "Volume"],
    tablefmt="github"
    )

    # =========================
    # FINAL MESSAGE
    # =========================
    message = (
        "📊 *Stocks for the Day*\n\n"

        "🔥 *Top Picks (Ranked)*\n"
        "```\n"
        f"{top_text}\n"
        "```\n\n"

        "🔹 Dashboard (Remaining Signals)\n"
        "```\n"
        f"{dashboard_table}\n"
        "```\n\n"

        "🔹 Inside Bar Screener\n"
        "```\n"
        f"{ib_table}\n"
        "```\n\n"

        "🔹 EMA Reversal Screener\n"
        "```\n"
        f"{ema_table}\n"
        "```"
    )

    if len(message) > 4000:
        message = message[:4000]

    print(message)
    send_to_telegram(message)


if __name__ == "__main__":
    run()
