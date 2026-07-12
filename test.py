import time
from collections import Counter
import pandas as pd
from playwright.sync_api import sync_playwright
import os
import requests
from tabulate import tabulate

DASHBOARD_URL = "https://chartink.com/dashboard/334725"
SCREENER_URL = "https://chartink.com/screener/2-3-4-week-insidebar-2026"
EMA_SCREENER_URL = "https://chartink.com/screener/10-20-ema-reversal-stocks"
CONSOLIDATION_SCREENER_URL = "https://chartink.com/screener/250-375-400-d-consolidation-25-range"
HEADLESS = True


def send_to_telegram(message, file_path=None):
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")

    if not BOT_TOKEN or not CHAT_ID:
        print("Missing Telegram credentials")
        return

    if file_path:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

        with open(file_path, "rb") as file:
            response = requests.post(
                url,
                data={
                    "chat_id": CHAT_ID,
                    "caption": message,
                    "parse_mode": "Markdown"
                },
                files={
                    "document": file
                }
            )
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }
        )

    print("Telegram response:", response.text)


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

        if volume_text:
            volume = int(volume_text.replace(",", ""))
        else:
            volume = 0

        results.append([symbol, price, change, volume])

    return results


def rank_stocks(widget_lists):
    counter = Counter()

    for lst in widget_lists:
        counter.update(lst)

    return counter.most_common()


def prioritize_and_sort_screener(screener_results, top_symbols, limit):

    def safe_price(row):
        try:
            return float(row[1].replace(",", ""))
        except:
            return float("inf")

    priority = []
    others = []

    for row in screener_results:
        if row[0] in top_symbols:
            priority.append(row)
        else:
            others.append(row)

    priority_sorted = sorted(priority, key=safe_price)
    others_sorted = sorted(others, key=safe_price)

    return (priority_sorted + others_sorted)[:limit]


def sort_screener_by_price(screener_results, limit):

    def safe_price(row):
        try:
            return float(row[1].replace(",", ""))
        except:
            return float("inf")

    return sorted(screener_results, key=safe_price)[:limit]


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()

        widget_lists = scrape_dashboard(page)

        if not widget_lists:
            send_to_telegram("No dashboard data.")
            return

        ranked = rank_stocks(widget_lists)

        ib_results = scrape_chartink_table(page, SCREENER_URL)
        ema_results = scrape_chartink_table(page, EMA_SCREENER_URL)
        consolidation_results = scrape_chartink_table(page, CONSOLIDATION_SCREENER_URL)

        ib_set = {s[0] for s in ib_results}
        ema_set = {s[0] for s in ema_results}
        consolidation_set = {s[0] for s in consolidation_results}

        browser.close()

    ranked = [r for r in ranked if r[1] >= 2]

    combined = []

    for stock, count in ranked:
        score = count * 10
        tags = []

        if stock in ib_set:
            tags.append("IB")

        if stock in ema_set:
            tags.append("EMA")

        if stock in consolidation_set:
            tags.append("CONS")

        combined.append((stock, count, score, "+".join(tags)))

    combined = sorted(combined, key=lambda x: x[2], reverse=True)

    top_picks = combined[:5]
    top_symbols = {s[0] for s in top_picks}

    if top_picks:
        top_text = "\n".join(
            [f"{i+1}. {s[0]} | Score:{s[2]} {s[3]}" for i, s in enumerate(top_picks)]
        )
    else:
        top_text = "No strong picks."

    remaining = [r for r in ranked if r[0] not in top_symbols][:5]

    df = pd.DataFrame(remaining, columns=["Stock", "Count"])
    df["Strength"] = df["Count"].apply(lambda x: "🔥" if x >= 3 else "⚡")

    dashboard_table = tabulate(
        df,
        headers="keys",
        tablefmt="github",
        showindex=False
    )

    ib_final = prioritize_and_sort_screener(ib_results, top_symbols, 10)
    ema_final = prioritize_and_sort_screener(ema_results, top_symbols, 10)
    cons_final = sort_screener_by_price(consolidation_results, 10)

    ib_table = tabulate(
        ib_final,
        headers=["Stock", "Price", "%Change", "Volume"],
        tablefmt="github"
    )

    cons_table = tabulate(
        cons_final,
        headers=["Stock", "Price", "%Change", "Volume"],
        tablefmt="github"
    )

    ema_table = tabulate(
        ema_final,
        headers=["Stock", "Price", "%Change", "Volume"],
        tablefmt="github"
    )

    watchlist = []

    watchlist.extend([s[0] for s in top_picks])
    watchlist.extend(df["Stock"].tolist())
    watchlist.extend([r[0] for r in ib_final])
    watchlist.extend([r[0] for r in cons_final])
    watchlist.extend([r[0] for r in ema_final])

    # Remove duplicates while preserving order
    watchlist = list(dict.fromkeys(watchlist))

    txt_filename = "watchlist.txt"

    with open(txt_filename, "w") as f:
        for stock in watchlist:
            f.write(stock + "\n")

    message = (
        "📊 *Stocks for the Day*\n\n"

        "*Top Picks (Ranked)*\n"
        f"{top_text}\n\n"

        "*Dashboard (Remaining Signals)*\n"
        "```\n"
        f"{dashboard_table}\n"
        "```\n\n"

        "*⚡Weekly Inside Bar*\n"
        "```\n"
        f"{ib_table}\n"
        "```\n\n"

        "*⚡⚡Long Consolidation*\n"
        "```\n"
        f"{cons_table}\n"
        "```\n\n"

        "*10/21 EMA Reversal*\n"
        "```\n"
        f"{ema_table}\n"
        "```"
    )

    if len(message) > 4000:
        message = message[:4000]

    print(message)
    send_to_telegram(message, txt_filename)


if __name__ == "__main__":
    run()
