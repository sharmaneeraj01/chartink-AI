import time
from collections import Counter
import pandas as pd
from playwright.sync_api import sync_playwright
import os
import requests
from tabulate import tabulate


# ============================================================
# URLs
# ============================================================

DASHBOARD_URL = "https://chartink.com/dashboard/334725"

SCREENER_URL = (
    "https://chartink.com/screener/"
    "close-above-supertrend-and-near-52-weeek-low-stock"
)

EMA_SCREENER_URL = (
    "https://chartink.com/screener/"
    "vivek-equity-5-pre-breakout"
)

CONSOLIDATION_SCREENER_URL = (
    "https://chartink.com/screener/"
    "supertrend-contraction-momentum-entry-above-swing-high-of-latest-green-zone-supertrend"
)

# NEW SCREENER
NEAR_HIGH_CONSOLIDATION_URL = (
    "https://chartink.com/screener/"
    "stocks-10-below-52-week-high-and-consolidating"
)

HEADLESS = True


# ============================================================
# TELEGRAM
# ============================================================

def send_to_telegram(message, file_path=None):

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")

    if not BOT_TOKEN or not CHAT_ID:
        print("Missing Telegram credentials")
        return

    # --------------------------------------------------------
    # Send text message
    # --------------------------------------------------------

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
    )

    print("Message:", response.text)

    # --------------------------------------------------------
    # Send TXT file
    # --------------------------------------------------------

    if file_path:

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

        with open(file_path, "rb") as file:

            response = requests.post(
                url,
                data={
                    "chat_id": CHAT_ID
                },
                files={
                    "document": file
                }
            )

        print("Document:", response.text)


# ============================================================
# SCRAPE DASHBOARD
# ============================================================

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


# ============================================================
# SCRAPE CHARTINK SCREENER
# ============================================================

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

            try:
                volume = int(
                    volume_text.replace(",", "")
                )
            except:
                volume = 0

        else:
            volume = 0

        results.append(
            [symbol, price, change, volume]
        )

    return results


# ============================================================
# RANK DASHBOARD STOCKS
# ============================================================

def rank_stocks(widget_lists):

    counter = Counter()

    for lst in widget_lists:
        counter.update(lst)

    return counter.most_common()


# ============================================================
# PRIORITIZE SCREENER STOCKS
# ============================================================

def prioritize_and_sort_screener(
    screener_results,
    top_symbols,
    limit
):

    def safe_price(row):

        try:
            return float(
                row[1].replace(",", "")
            )

        except:
            return float("inf")

    priority = []
    others = []

    for row in screener_results:

        if row[0] in top_symbols:
            priority.append(row)

        else:
            others.append(row)

    priority_sorted = sorted(
        priority,
        key=safe_price
    )

    others_sorted = sorted(
        others,
        key=safe_price
    )

    return (
        priority_sorted +
        others_sorted
    )[:limit]


# ============================================================
# SORT SCREENER BY PRICE
# ============================================================

def sort_screener_by_price(
    screener_results,
    limit
):

    def safe_price(row):

        try:
            return float(
                row[1].replace(",", "")
            )

        except:
            return float("inf")

    return sorted(
        screener_results,
        key=safe_price
    )[:limit]


# ============================================================
# MAIN RUN
# ============================================================

def run():

    # --------------------------------------------------------
    # OPEN BROWSER
    # --------------------------------------------------------

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=HEADLESS
        )

        page = browser.new_page()

        # ----------------------------------------------------
        # DASHBOARD
        # ----------------------------------------------------

        widget_lists = scrape_dashboard(page)

        if not widget_lists:

            send_to_telegram(
                "No dashboard data."
            )

            browser.close()

            return

        ranked = rank_stocks(
            widget_lists
        )

        # ----------------------------------------------------
        # EXISTING SCREENER 1
        # Close above Supertrend & near 52W low
        # ----------------------------------------------------

        ib_results = scrape_chartink_table(
            page,
            SCREENER_URL
        )

        # ----------------------------------------------------
        # EXISTING SCREENER 2
        # 5% Pre-Breakout
        # ----------------------------------------------------

        ema_results = scrape_chartink_table(
            page,
            EMA_SCREENER_URL
        )

        # ----------------------------------------------------
        # EXISTING SCREENER 3
        # Supertrend contraction
        # ----------------------------------------------------

        consolidation_results = scrape_chartink_table(
            page,
            CONSOLIDATION_SCREENER_URL
        )

        # ----------------------------------------------------
        # NEW SCREENER 4
        # 10% below 52W high & consolidating
        # ----------------------------------------------------

        near_high_consolidation_results = (
            scrape_chartink_table(
                page,
                NEAR_HIGH_CONSOLIDATION_URL
            )
        )

        # ----------------------------------------------------
        # CREATE SETS
        # ----------------------------------------------------

        ib_set = {
            s[0]
            for s in ib_results
        }

        ema_set = {
            s[0]
            for s in ema_results
        }

        consolidation_set = {
            s[0]
            for s in consolidation_results
        }

        near_high_consolidation_set = {
            s[0]
            for s in near_high_consolidation_results
        }

        browser.close()

    # ========================================================
    # FILTER DASHBOARD RANKING
    # ========================================================

    ranked = [
        r for r in ranked
        if r[1] >= 2
    ]

    combined = []

    # ========================================================
    # COMBINE SIGNALS
    # ========================================================

    for stock, count in ranked:

        score = count * 10

        tags = []

        # Existing signal 1
        if stock in ib_set:
            tags.append("IB")

        # Existing signal 2
        if stock in ema_set:
            tags.append("EMA")

        # Existing signal 3
        if stock in consolidation_set:
            tags.append("CONS")

        # NEW signal 4
        if stock in near_high_consolidation_set:
            tags.append("NH-CONS")

        combined.append(
            (
                stock,
                count,
                score,
                "+".join(tags)
            )
        )

    # ========================================================
    # SORT BY SCORE
    # ========================================================

    combined = sorted(
        combined,
        key=lambda x: x[2],
        reverse=True
    )

    # ========================================================
    # TOP PICKS
    # ========================================================

    top_picks = combined[:5]

    top_symbols = {
        s[0]
        for s in top_picks
    }

    if top_picks:

        top_text = "\n".join(
            [
                f"{i+1}. {s[0]} | "
                f"Score:{s[2]} "
                f"{s[3]}"
                for i, s in enumerate(top_picks)
            ]
        )

    else:

        top_text = "No strong picks."

    # ========================================================
    # REMAINING DASHBOARD SIGNALS
    # ========================================================

    remaining = [
        r
        for r in ranked
        if r[0] not in top_symbols
    ][:5]

    df = pd.DataFrame(
        remaining,
        columns=[
            "Stock",
            "Count"
        ]
    )

    df["Strength"] = df[
        "Count"
    ].apply(
        lambda x:
        "🔥" if x >= 3 else "⚡"
    )

    dashboard_table = tabulate(
        df,
        headers="keys",
        tablefmt="github",
        showindex=False
    )

    # ========================================================
    # FINAL SCREENER RESULTS
    # ========================================================

    # --------------------------------------------------------
    # 1. IB
    # --------------------------------------------------------

    ib_final = prioritize_and_sort_screener(
        ib_results,
        top_symbols,
        10
    )

    # --------------------------------------------------------
    # 2. EMA
    # --------------------------------------------------------

    ema_final = prioritize_and_sort_screener(
        ema_results,
        top_symbols,
        15
    )

    # --------------------------------------------------------
    # 3. CONS
    # --------------------------------------------------------

    cons_final = sort_screener_by_price(
        consolidation_results,
        15
    )

    # --------------------------------------------------------
    # 4. NEW NH-CONS
    # --------------------------------------------------------

    near_high_consolidation_final = (
        sort_screener_by_price(
            near_high_consolidation_results,
            15
        )
    )

    # ========================================================
    # CREATE TABLES
    # ========================================================

    ib_table = tabulate(
        ib_final,
        headers=[
            "Stock",
            "Price",
            "%Change",
            "Volume"
        ],
        tablefmt="github"
    )

    cons_table = tabulate(
        cons_final,
        headers=[
            "Stock",
            "Price",
            "%Change",
            "Volume"
        ],
        tablefmt="github"
    )

    ema_table = tabulate(
        ema_final,
        headers=[
            "Stock",
            "Price",
            "%Change",
            "Volume"
        ],
        tablefmt="github"
    )

    near_high_consolidation_table = tabulate(
        near_high_consolidation_final,
        headers=[
            "Stock",
            "Price",
            "%Change",
            "Volume"
        ],
        tablefmt="github"
    )

    # ========================================================
    # CREATE WATCHLIST
    # ========================================================

    watchlist = []

    # Top dashboard picks
    watchlist.extend(
        [
            s[0]
            for s in top_picks
        ]
    )

    # Remaining dashboard signals
    watchlist.extend(
        df["Stock"].tolist()
    )

    # IB
    watchlist.extend(
        [
            r[0]
            for r in ib_final
        ]
    )

    # CONS
    watchlist.extend(
        [
            r[0]
            for r in cons_final
        ]
    )

    # EMA
    watchlist.extend(
        [
            r[0]
            for r in ema_final
        ]
    )

    # NEW NH-CONS
    watchlist.extend(
        [
            r[0]
            for r in near_high_consolidation_final
        ]
    )

    # --------------------------------------------------------
    # Remove duplicates while preserving order
    # --------------------------------------------------------

    watchlist = list(
        dict.fromkeys(watchlist)
    )

    # ========================================================
    # SAVE WATCHLIST
    # ========================================================

    txt_filename = "watchlist.txt"

    with open(
        txt_filename,
        "w"
    ) as f:

        for stock in watchlist:
            f.write(stock + "\n")

    # ========================================================
    # TELEGRAM MESSAGE
    # ========================================================

    message = (

        "📊 *Stocks for the Day*\n\n"

        # ----------------------------------------------------
        # TOP PICKS
        # ----------------------------------------------------

        "*Top Picks (Ranked)*\n"
        f"{top_text}\n\n"

        # ----------------------------------------------------
        # DASHBOARD
        # ----------------------------------------------------

        "*Dashboard (Remaining Signals)*\n"
        "```\n"
        f"{dashboard_table}\n"
        "```\n\n"

        # ----------------------------------------------------
        # IB
        # ----------------------------------------------------

        "*⚡ Close above Supertrend & near 52W low*\n"
        "```\n"
        f"{ib_table}\n"
        "```\n\n"

        # ----------------------------------------------------
        # CONS
        # ----------------------------------------------------

        "*⚡⚡ Supertrend Contraction "
        "Swing High Breakout wait*\n"
        "```\n"
        f"{cons_table}\n"
        "```\n\n"

        # ----------------------------------------------------
        # EMA
        # ----------------------------------------------------

        "*⚡⚡⚡ 5% Pre-Breakout*\n"
        "```\n"
        f"{ema_table}\n"
        "```\n\n"

        # ----------------------------------------------------
        # NEW NH-CONS
        # ----------------------------------------------------

        "*🔥 Near 52W High & Consolidating*\n"
        "```\n"
        f"{near_high_consolidation_table}\n"
        "```"
    )

    # ========================================================
    # PRINT
    # ========================================================

    print(message)

    # ========================================================
    # SEND TELEGRAM
    # ========================================================

    send_to_telegram(
        message,
        txt_filename
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run()
