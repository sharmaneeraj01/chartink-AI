import time
from collections import Counter
import pandas as pd
from playwright.sync_api import sync_playwright
import os
import requests
from tabulate import tabulate
import json
from datetime import datetime


# ============================================================
# URLs
# ============================================================

DASHBOARD_URL = "https://chartink.com/dashboard/334725"

# Screener 1:
# Close above Supertrend & near 52-week low
SCREENER_URL = (
    "https://chartink.com/screener/"
    "close-above-supertrend-and-near-52-weeek-low-stock"
)

# Screener 2:
# 5% Pre-Breakout
EMA_SCREENER_URL = (
    "https://chartink.com/screener/"
    "vivek-equity-5-pre-breakout"
)

# Screener 3:
# Supertrend Contraction
CONSOLIDATION_SCREENER_URL = (
    "https://chartink.com/screener/"
    "supertrend-contraction-momentum-entry-above-swing-high-of-latest-green-zone-supertrend"
)

# Screener 4:
# 10% below 52W high & consolidating
NEAR_HIGH_CONSOLIDATION_URL = (
    "https://chartink.com/screener/"
    "stocks-10-below-52-week-high-and-consolidating"
)


# ============================================================
# SETTINGS
# ============================================================

HEADLESS = True

# Persistent history file for the first screener
IB_HISTORY_FILE = "ib_5day_history.json"

# Number of trading-day lists to remember
IB_HISTORY_DAYS = 5


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
# TRADING DAY CHECK
# ============================================================

def is_weekend():

    # Monday = 0
    # Tuesday = 1
    # Wednesday = 2
    # Thursday = 3
    # Friday = 4
    # Saturday = 5
    # Sunday = 6

    return datetime.now().weekday() >= 5


# ============================================================
# LOAD IB HISTORY
# ============================================================

def load_ib_history():

    if not os.path.exists(IB_HISTORY_FILE):
        return []

    try:

        with open(
            IB_HISTORY_FILE,
            "r"
        ) as f:

            history = json.load(f)

        if not isinstance(history, list):
            return []

        return history

    except Exception as e:

        print(
            f"Could not read IB history: {e}"
        )

        return []


# ============================================================
# SAVE IB HISTORY
# ============================================================

def save_ib_history(history):

    try:

        with open(
            IB_HISTORY_FILE,
            "w"
        ) as f:

            json.dump(
                history,
                f,
                indent=4
            )

    except Exception as e:

        print(
            f"Could not save IB history: {e}"
        )


# ============================================================
# UPDATE 5-TRADING-DAY IB HISTORY
# ============================================================

def update_ib_history(ib_results):

    # --------------------------------------------------------
    # Do NOT create/update history on Saturday or Sunday
    # --------------------------------------------------------

    if is_weekend():

        print(
            "Weekend detected - "
            "IB history will NOT be updated."
        )

        return load_ib_history()

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    # --------------------------------------------------------
    # Extract today's IB stock list
    # --------------------------------------------------------

    today_stocks = sorted(
        list(
            {
                row[0]
                for row in ib_results
            }
        )
    )

    print(
        f"\nToday's IB list: "
        f"{len(today_stocks)} stocks"
    )

    # --------------------------------------------------------
    # Load previous history
    # --------------------------------------------------------

    history = load_ib_history()

    # --------------------------------------------------------
    # Remove today's previous entry if script
    # runs more than once today
    # --------------------------------------------------------

    history = [
        entry
        for entry in history
        if entry.get("date") != today
    ]

    # --------------------------------------------------------
    # Add today's generated list
    # --------------------------------------------------------

    history.append(
        {
            "date": today,
            "stocks": today_stocks
        }
    )

    # --------------------------------------------------------
    # Sort chronologically
    # --------------------------------------------------------

    history = sorted(
        history,
        key=lambda x: x.get("date", "")
    )

    # --------------------------------------------------------
    # Keep ONLY latest 5 generated trading-day lists
    # --------------------------------------------------------

    history = history[-IB_HISTORY_DAYS:]

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_ib_history(history)

    print(
        "\nStored IB trading-day history:"
    )

    for entry in history:

        print(
            f"{entry['date']} : "
            f"{len(entry['stocks'])} stocks"
        )

    return history


# ============================================================
# FIND STOCKS THAT APPEARED IN IB DURING LAST 5 TRADING DAYS
# ============================================================

def get_5day_ib_stocks(history):

    stocks = set()

    for entry in history:

        stocks.update(
            entry.get(
                "stocks",
                []
            )
        )

    return stocks


# ============================================================
# FIND HOW MANY TRADING DAYS AGO STOCK APPEARED IN IB
# ============================================================

def get_ib_days_ago(history, stock):

    """
    Returns the most recent trading-day position
    on which the stock appeared in IB.

    0 = today
    1 = previous generated trading-day list
    2 = two trading days ago
    etc.
    """

    if not history:
        return None

    # Make sure newest is first
    history_newest_first = sorted(
        history,
        key=lambda x: x.get("date", ""),
        reverse=True
    )

    for index, entry in enumerate(
        history_newest_first
    ):

        if stock in entry.get(
            "stocks",
            []
        ):

            return index

    return None


# ============================================================
# SCRAPE DASHBOARD
# ============================================================

def scrape_dashboard(page):

    widget_results = []

    print(
        "Opening dashboard..."
    )

    page.goto(
        DASHBOARD_URL
    )

    page.wait_for_load_state(
        "networkidle"
    )

    page.wait_for_timeout(
        5000
    )

    page.mouse.wheel(
        0,
        5000
    )

    page.wait_for_timeout(
        3000
    )

    tables = page.query_selector_all(
        "table"
    )

    for table in tables:

        stocks = table.query_selector_all(
            "a"
        )

        symbols = []

        for s in stocks:

            text = s.inner_text().strip()

            if (
                text.isupper()
                and 2 <= len(text) <= 15
            ):

                symbols.append(text)

        symbols = list(
            set(symbols)
        )

        if len(symbols) >= 5:

            widget_results.append(
                symbols
            )

    return widget_results


# ============================================================
# SCRAPE CHARTINK SCREENER
# ============================================================

def scrape_chartink_table(page, url):

    results = []

    print(
        f"\nRunning screener: {url}"
    )

    page.goto(url)

    page.wait_for_load_state(
        "networkidle"
    )

    page.wait_for_timeout(
        5000
    )

    rows = page.query_selector_all(
        "table tbody tr"
    )

    for row in rows:

        cols = row.query_selector_all(
            "td"
        )

        if len(cols) < 6:
            continue

        symbol = cols[2].inner_text().strip()
        price = cols[3].inner_text().strip()
        change = cols[4].inner_text().strip()

        volume_text = (
            cols[5]
            .inner_text()
            .strip()
        )

        if volume_text:

            try:

                volume = int(
                    volume_text.replace(
                        ",",
                        ""
                    )
                )

            except:

                volume = 0

        else:

            volume = 0

        results.append(
            [
                symbol,
                price,
                change,
                volume
            ]
        )

    print(
        f"Found {len(results)} stocks"
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
                row[1].replace(
                    ",",
                    ""
                )
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
                row[1].replace(
                    ",",
                    ""
                )
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

    # ========================================================
    # OPEN BROWSER
    # ========================================================

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=HEADLESS
        )

        page = browser.new_page()

        # ====================================================
        # DASHBOARD
        # ====================================================

        widget_lists = scrape_dashboard(
            page
        )

        if not widget_lists:

            send_to_telegram(
                "No dashboard data."
            )

            browser.close()

            return

        ranked = rank_stocks(
            widget_lists
        )

        # ====================================================
        # SCREENER 1
        # Close above Supertrend & near 52W low
        # ====================================================

        ib_results = scrape_chartink_table(
            page,
            SCREENER_URL
        )

        # ====================================================
        # SCREENER 2
        # 5% Pre-Breakout
        # ====================================================

        ema_results = scrape_chartink_table(
            page,
            EMA_SCREENER_URL
        )

        # ====================================================
        # SCREENER 3
        # Supertrend Contraction
        # ====================================================

        consolidation_results = (
            scrape_chartink_table(
                page,
                CONSOLIDATION_SCREENER_URL
            )
        )

        # ====================================================
        # SCREENER 4
        # 10% Below 52W High & Consolidating
        # ====================================================

        near_high_consolidation_results = (
            scrape_chartink_table(
                page,
                NEAR_HIGH_CONSOLIDATION_URL
            )
        )

        # ====================================================
        # UPDATE 5-TRADING-DAY IB HISTORY
        # ====================================================

        ib_history = update_ib_history(
            ib_results
        )

        # ====================================================
        # ALL STOCKS SEEN IN IB DURING LAST 5 TRADING DAYS
        # ====================================================

        ib_5day_stocks = (
            get_5day_ib_stocks(
                ib_history
            )
        )

        # ====================================================
        # CURRENT SCREENER SETS
        # ====================================================

        ib_set = {
            row[0]
            for row in ib_results
        }

        ema_set = {
            row[0]
            for row in ema_results
        }

        consolidation_set = {
            row[0]
            for row in consolidation_results
        }

        near_high_consolidation_set = {
            row[0]
            for row in
            near_high_consolidation_results
        }

        # ====================================================
        # SPECIAL SIGNAL
        #
        # IB during last 5 trading days
        # +
        # CONS today
        # ====================================================

        five_day_ib_cons_set = (
            consolidation_set
            &
            ib_5day_stocks
        )

        print(
            "\nIB → CONS WATCH:"
        )

        print(
            sorted(
                five_day_ib_cons_set
            )
        )

        browser.close()

    # ========================================================
    # FILTER DASHBOARD RANKING
    # ========================================================

    ranked = [
        r
        for r in ranked
        if r[1] >= 2
    ]

    combined = []

    # ========================================================
    # COMBINE SIGNALS
    # ========================================================

    for stock, count in ranked:

        score = count * 10

        tags = []

        # ----------------------------------------------------
        # Current IB
        # ----------------------------------------------------

        if stock in ib_set:

            tags.append(
                "IB"
            )

        # ----------------------------------------------------
        # Current EMA
        # ----------------------------------------------------

        if stock in ema_set:

            tags.append(
                "EMA"
            )

        # ----------------------------------------------------
        # Current CONS
        # ----------------------------------------------------

        if stock in consolidation_set:

            tags.append(
                "CONS"
            )

        # ----------------------------------------------------
        # Near High Consolidation
        # ----------------------------------------------------

        if stock in near_high_consolidation_set:

            tags.append(
                "NH-CONS"
            )

        # ----------------------------------------------------
        # IB → CONS during last 5 trading days
        # ----------------------------------------------------

        if stock in five_day_ib_cons_set:

            tags.append(
                "5D-IB"
            )

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
                for i, s in enumerate(
                    top_picks
                )
            ]
        )

    else:

        top_text = (
            "No strong picks."
        )

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
        "🔥"
        if x >= 3
        else "⚡"
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
    # IB
    # --------------------------------------------------------

    ib_final = (
        prioritize_and_sort_screener(
            ib_results,
            top_symbols,
            10
        )
    )

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    ema_final = (
        prioritize_and_sort_screener(
            ema_results,
            top_symbols,
            15
        )
    )

    # --------------------------------------------------------
    # CONS
    # --------------------------------------------------------

    cons_final = (
        sort_screener_by_price(
            consolidation_results,
            15
        )
    )

    # --------------------------------------------------------
    # NH-CONS
    # --------------------------------------------------------

    near_high_consolidation_final = (
        sort_screener_by_price(
            near_high_consolidation_results,
            15
        )
    )

    # ========================================================
    # SPECIAL IB → CONS WATCH TABLE
    # ========================================================

    ib_cons_watch = []

    for row in consolidation_results:

        stock = row[0]

        if stock in five_day_ib_cons_set:

            days_ago = get_ib_days_ago(
                ib_history,
                stock
            )

            if days_ago == 0:

                ib_age = "TODAY"

            elif days_ago == 1:

                ib_age = "1D ago"

            elif days_ago is not None:

                ib_age = (
                    f"{days_ago}D ago"
                )

            else:

                ib_age = ""

            ib_cons_watch.append(
                [
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    ib_age
                ]
            )

    # ========================================================
    # SPECIAL TABLE
    # ========================================================

    if ib_cons_watch:

        ib_cons_watch_table = tabulate(
            ib_cons_watch,
            headers=[
                "Stock",
                "Price",
                "%Change",
                "Volume",
                "IB"
            ],
            tablefmt="github"
        )

    else:

        ib_cons_watch_table = (
            "No IB → CONS stocks today."
        )

    # ========================================================
    # NORMAL TABLES
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

    # --------------------------------------------------------
    # Dashboard Top Picks
    # --------------------------------------------------------

    watchlist.extend(
        [
            s[0]
            for s in top_picks
        ]
    )

    # --------------------------------------------------------
    # Dashboard Remaining
    # --------------------------------------------------------

    watchlist.extend(
        df["Stock"].tolist()
    )

    # --------------------------------------------------------
    # ALL IB RESULTS
    # --------------------------------------------------------

    watchlist.extend(
        [
            r[0]
            for r in ib_results
        ]
    )

    # --------------------------------------------------------
    # ALL CONS RESULTS
    # --------------------------------------------------------

    watchlist.extend(
        [
            r[0]
            for r in consolidation_results
        ]
    )

    # --------------------------------------------------------
    # ALL EMA RESULTS
    # --------------------------------------------------------

    watchlist.extend(
        [
            r[0]
            for r in ema_results
        ]
    )

    # --------------------------------------------------------
    # ALL NH-CONS RESULTS
    # --------------------------------------------------------

    watchlist.extend(
        [
            r[0]
            for r in
            near_high_consolidation_results
        ]
    )

    # --------------------------------------------------------
    # Remove duplicates while preserving order
    # --------------------------------------------------------

    watchlist = list(
        dict.fromkeys(
            watchlist
        )
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

            f.write(
                stock + "\n"
            )

    # ========================================================
    # TELEGRAM MESSAGE
    # ========================================================

    message = (

        "📊 *Stocks for the Day*\n\n"

        # ====================================================
        # TOP PICKS
        # ====================================================

        "*Top Picks (Ranked)*\n"
        f"{top_text}\n\n"

        # ====================================================
        # DASHBOARD
        # ====================================================

        "*Dashboard (Remaining Signals)*\n"
        "```\n"
        f"{dashboard_table}\n"
        "```\n\n"

        # ====================================================
        # IB
        # ====================================================

        "*⚡ Close above Supertrend & near 52W low*\n"
        "```\n"
        f"{ib_table}\n"
        "```\n\n"

        # ====================================================
        # SPECIAL IB → CONS WATCH
        # ====================================================

        "*🔥🔥🔥 IB → CONS WATCH 🔥🔥🔥*\n"
        "_IB during last 5 trading days + CONS today_\n"
        "IB = most recent IB appearance_\n"
        "```\n"
        f"{ib_cons_watch_table}\n"
        "```\n\n"

        # ====================================================
        # NORMAL CONS
        # ====================================================

        "*⚡⚡ Supertrend Contraction "
        "Swing High Breakout wait*\n"
        "```\n"
        f"{cons_table}\n"
        "```\n\n"

        # ====================================================
        # EMA
        # ====================================================

        "*⚡⚡⚡ 5% Pre-Breakout*\n"
        "```\n"
        f"{ema_table}\n"
        "```\n\n"

        # ====================================================
        # NH-CONS
        # ====================================================

        "*🔥⚡ 10% Below 52W High & Consolidating*\n"
        "```\n"
        f"{near_high_consolidation_table}\n"
        "```"
    )

    # ========================================================
    # PRINT
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )

    print(
        message
    )

    print(
        "=" * 80
    )

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
