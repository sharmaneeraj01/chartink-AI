import os
import json
import requests

from collections import Counter
from datetime import datetime

from tabulate import tabulate
from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

HEADLESS = True

DASHBOARD_URL = (
    "https://chartink.com/dashboard/334725"
)

# ------------------------------------------------------------
# IB
# Close above Supertrend & near 52-week low
# ------------------------------------------------------------

SCREENER_URL = (
    "https://chartink.com/screener/"
    "close-above-supertrend-and-near-52-weeek-low-stock"
)

# ------------------------------------------------------------
# EMA
# 5% Pre-Breakout
# ------------------------------------------------------------

EMA_SCREENER_URL = (
    "https://chartink.com/screener/"
    "vivek-equity-5-pre-breakout"
)

# ------------------------------------------------------------
# CONS
# Supertrend Contraction / Swing High Breakout
# ------------------------------------------------------------

CONSOLIDATION_SCREENER_URL = (
    "https://chartink.com/screener/"
    "supertrend-contraction-momentum-entry-above-swing-high-of-latest-green-zone-supertrend"
)

# ------------------------------------------------------------
# NH-CONS
# 10% Below 52W High & Consolidating
# ------------------------------------------------------------

NEAR_HIGH_CONSOLIDATION_URL = (
    "https://chartink.com/screener/"
    "stocks-10-below-52-week-high-and-consolidating"
)


# ============================================================
# FILES
# ============================================================

IB_HISTORY_FILE = "ib_5day_history.json"
WATCHLIST_FILE = "watchlist.txt"

# Keep latest 5 generated trading-day IB lists
IB_HISTORY_DAYS = 5


# ============================================================
# TELEGRAM
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def send_telegram_message(message):

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "Telegram credentials not found."
        )

        return

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=30
        )

        print(
            "Telegram message:",
            response.text
        )

    except Exception as e:

        print(
            "Telegram message error:",
            e
        )


def send_telegram_file(file_path):

    if not BOT_TOKEN or not CHAT_ID:

        return

    if not os.path.exists(file_path):

        print(
            f"File does not exist: {file_path}"
        )

        return

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendDocument"
    )

    try:

        with open(
            file_path,
            "rb"
        ) as file:

            response = requests.post(
                url,
                data={
                    "chat_id": CHAT_ID
                },
                files={
                    "document": file
                },
                timeout=30
            )

        print(
            "Telegram document:",
            response.text
        )

    except Exception as e:

        print(
            "Telegram document error:",
            e
        )


# ============================================================
# IB HISTORY
# ============================================================

def load_ib_history():

    if not os.path.exists(
        IB_HISTORY_FILE
    ):

        return []

    try:

        with open(
            IB_HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            history = json.load(f)

        if not isinstance(
            history,
            list
        ):

            return []

        return history

    except Exception as e:

        print(
            "IB history read error:",
            e
        )

        return []


def save_ib_history(history):

    try:

        with open(
            IB_HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                history,
                f,
                indent=4
            )

    except Exception as e:

        print(
            "IB history save error:",
            e
        )


def is_weekend():

    return datetime.now().weekday() >= 5


def update_ib_history(
    ib_results
):

    history = load_ib_history()

    # --------------------------------------------------------
    # Never save Saturday / Sunday
    # --------------------------------------------------------

    if is_weekend():

        print(
            "Weekend - IB history not updated."
        )

        return history

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    # --------------------------------------------------------
    # Today's IB stocks
    # --------------------------------------------------------

    today_stocks = sorted(
        {
            row[0]
            for row in ib_results
            if row and row[0]
        }
    )

    print(
        f"\nToday's IB list: "
        f"{len(today_stocks)} stocks"
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # Remove today's existing entry first.
    #
    # Therefore running the script twice on the same day
    # does NOT create two history entries.
    # --------------------------------------------------------

    history = [
        entry
        for entry in history
        if entry.get("date") != today
    ]

    # --------------------------------------------------------
    # Add today's list
    # --------------------------------------------------------

    history.append(
        {
            "date": today,
            "stocks": today_stocks
        }
    )

    # --------------------------------------------------------
    # Sort oldest -> newest
    # --------------------------------------------------------

    history.sort(
        key=lambda x: x.get(
            "date",
            ""
        )
    )

    # --------------------------------------------------------
    # Keep only latest 5 generated trading days
    # --------------------------------------------------------

    history = history[
        -IB_HISTORY_DAYS:
    ]

    save_ib_history(
        history
    )

    print(
        "\nStored IB trading-day history:"
    )

    for entry in history:

        print(
            f"{entry['date']} : "
            f"{len(entry['stocks'])} stocks"
        )

    return history


def get_5day_ib_stocks(
    history
):

    stocks = set()

    for entry in history:

        stocks.update(
            entry.get(
                "stocks",
                []
            )
        )

    return stocks


def get_ib_days_ago(
    history,
    stock
):

    # Newest first
    newest_first = sorted(
        history,
        key=lambda x: x.get(
            "date",
            ""
        ),
        reverse=True
    )

    for index, entry in enumerate(
        newest_first
    ):

        if stock in entry.get(
            "stocks",
            []
        ):

            return index

    return None


# ============================================================
# PLAYWRIGHT HELPERS
# ============================================================

def load_page(
    page,
    url
):

    print(
        f"\nOpening: {url}"
    )

    try:

        # IMPORTANT:
        # Do NOT use networkidle.
        # Chartink can keep network activity alive.
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000
        )

    except Exception as e:

        print(
            f"Page load warning: {e}"
        )

    # Give Chartink time to populate table
    page.wait_for_timeout(
        5000
    )


# ============================================================
# DASHBOARD SCRAPER
# ============================================================

def scrape_dashboard(
    page
):

    print(
        "\nOpening dashboard..."
    )

    load_page(
        page,
        DASHBOARD_URL
    )

    # --------------------------------------------------------
    # One controlled scroll.
    # NO LOOP.
    # --------------------------------------------------------

    page.mouse.wheel(
        0,
        4000
    )

    page.wait_for_timeout(
        2000
    )

    tables = page.query_selector_all(
        "table"
    )

    print(
        f"Dashboard tables found: "
        f"{len(tables)}"
    )

    widget_results = []

    for table in tables:

        symbols = []

        links = table.query_selector_all(
            "a"
        )

        for link in links:

            try:

                symbol = (
                    link
                    .inner_text()
                    .strip()
                    .upper()
                )

            except:

                continue

            # Basic symbol check
            if (
                2 <= len(symbol) <= 15
                and symbol.isupper()
                and symbol.replace(
                    "-",
                    ""
                ).replace(
                    "&",
                    ""
                ).isalnum()
            ):

                symbols.append(
                    symbol
                )

        # Remove duplicates
        symbols = list(
            dict.fromkeys(
                symbols
            )
        )

        if len(symbols) >= 5:

            widget_results.append(
                symbols
            )

    print(
        f"Dashboard widgets captured: "
        f"{len(widget_results)}"
    )

    return widget_results


# ============================================================
# CHARTINK SCREENER SCRAPER
# ============================================================

def scrape_chartink_table(
    page,
    url
):

    results = []

    print(
        f"\nRunning screener: {url}"
    )

    load_page(
        page,
        url
    )

    # One controlled scroll only
    page.mouse.wheel(
        0,
        2500
    )

    page.wait_for_timeout(
        2000
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

        try:

            symbol = (
                cols[2]
                .inner_text()
                .strip()
                .upper()
            )

            price = (
                cols[3]
                .inner_text()
                .strip()
            )

            change = (
                cols[4]
                .inner_text()
                .strip()
            )

            volume = (
                cols[5]
                .inner_text()
                .strip()
            )

        except:

            continue

        if not symbol:

            continue

        results.append(
            [
                symbol,
                price,
                change,
                volume
            ]
        )

    # --------------------------------------------------------
    # Remove duplicate symbols
    # --------------------------------------------------------

    unique = []

    seen = set()

    for row in results:

        if row[0] not in seen:

            seen.add(
                row[0]
            )

            unique.append(
                row
            )

    print(
        f"Found {len(unique)} stocks"
    )

    return unique


# ============================================================
# RANK DASHBOARD
# ============================================================

def rank_stocks(
    widget_lists
):

    counter = Counter()

    for stock_list in widget_lists:

        counter.update(
            stock_list
        )

    return counter.most_common()


# ============================================================
# PRICE SORT
# ============================================================

def price_value(row):

    try:

        return float(
            str(row[1])
            .replace(
                ",",
                ""
            )
        )

    except:

        return float(
            "inf"
        )


def sort_by_price(
    results,
    limit
):

    return sorted(
        results,
        key=price_value
    )[:limit]


# ============================================================
# PRIORITIZE TOP DASHBOARD STOCKS
# ============================================================

def prioritize_screener(
    results,
    top_symbols,
    limit
):

    priority = []
    others = []

    for row in results:

        if row[0] in top_symbols:

            priority.append(
                row
            )

        else:

            others.append(
                row
            )

    priority.sort(
        key=price_value
    )

    others.sort(
        key=price_value
    )

    return (
        priority +
        others
    )[:limit]


# ============================================================
# STANDARD TABLE
# ============================================================

def make_table(
    rows
):

    if not rows:

        return "No stocks found."

    return tabulate(
        rows,
        headers=[
            "Stock",
            "Price",
            "%Change",
            "Volume"
        ],
        tablefmt="github"
    )


# ============================================================
# SPECIAL IB → CONS WATCH
# ============================================================

def build_ib_cons_watch(
    consolidation_results,
    ib_history
):

    five_day_ib_stocks = (
        get_5day_ib_stocks(
            ib_history
        )
    )

    result = []

    for row in consolidation_results:

        stock = row[0]

        if stock not in five_day_ib_stocks:

            continue

        days_ago = get_ib_days_ago(
            ib_history,
            stock
        )

        if days_ago == 0:

            age = "TODAY"

        elif days_ago == 1:

            age = "1D ago"

        elif days_ago is not None:

            age = f"{days_ago}D ago"

        else:

            age = "-"

        result.append(
            [
                row[0],
                row[1],
                row[2],
                row[3],
                age
            ]
        )

    return result


# ============================================================
# CREATE WATCHLIST.TXT
# ============================================================

def create_watchlist_file(
    top_picks,
    remaining,
    ib_results,
    ib_cons_watch,
    consolidation_results,
    ema_results,
    near_high_results
):

    with open(
        WATCHLIST_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        # ----------------------------------------------------
        # TOP PICKS
        # ----------------------------------------------------

        f.write(
            "=" * 60 + "\n"
        )

        f.write(
            "TOP PICKS\n"
        )

        f.write(
            "=" * 60 + "\n"
        )

        for stock, count, score, tags in top_picks:

            line = (
                f"{stock} | "
                f"Score:{score}"
            )

            if tags:

                line += (
                    f" | {tags}"
                )

            f.write(
                line + "\n"
            )

        f.write("\n")

        # ----------------------------------------------------
        # DASHBOARD REMAINING
        # ----------------------------------------------------

        f.write(
            "=" * 60 + "\n"
        )

        f.write(
            "DASHBOARD REMAINING SIGNALS\n"
        )

        f.write(
            "=" * 60 + "\n"
        )

        for stock, count in remaining:

            f.write(
                f"{stock} | Count:{count}\n"
            )

        f.write("\n")

        # ----------------------------------------------------
        # IB
        # ----------------------------------------------------

        f.write(
            "=" * 60 + "\n"
        )

        f.write(
            "IB - CLOSE ABOVE SUPERTREND & NEAR 52W LOW\n"
        )

        f.write(
            "=" * 60 + "\n"
        )

        for row in ib_results:

            f.write(
                f"{row[0]} | "
                f"Price:{row[1]} | "
                f"Change:{row[2]} | "
                f"Volume:{row[3]}\n"
            )

        f.write("\n")

        # ----------------------------------------------------
        # IB → CONS WATCH
        # ----------------------------------------------------

        f.write(
            "=" * 60 + "\n"
        )

        f.write(
            "🔥 IB → CONS WATCH\n"
        )

        f.write(
            "IB during last 5 trading days + CONS today\n"
        )

        f.write(
            "=" * 60 + "\n"
        )

        if ib_cons_watch:

            for row in ib_cons_watch:

                f.write(
                    f"{row[0]} | "
                    f"Price:{row[1]} | "
                    f"Change:{row[2]} | "
                    f"Volume:{row[3]} | "
                    f"IB:{row[4]}\n"
                )

        else:

            f.write(
                "No IB → CONS stocks today.\n"
            )

        f.write("\n")

        # ----------------------------------------------------
        # CONS
        # ----------------------------------------------------

        f.write(
            "=" * 60 + "\n"
        )

        f.write(
            "CONS - SUPERTREND CONTRACTION\n"
        )

        f.write(
            "=" * 60 + "\n"
        )

        for row in consolidation_results:

            f.write(
                f"{row[0]} | "
                f"Price:{row[1]} | "
                f"Change:{row[2]} | "
                f"Volume:{row[3]}\n"
            )

        f.write("\n")

        # ----------------------------------------------------
        # EMA
        # ----------------------------------------------------

        f.write(
            "=" * 60 + "\n"
        )

        f.write(
            "5% PRE-BREAKOUT\n"
        )

        f.write(
            "=" * 60 + "\n"
        )

        for row in ema_results:

            f.write(
                f"{row[0]} | "
                f"Price:{row[1]} | "
                f"Change:{row[2]} | "
                f"Volume:{row[3]}\n"
            )

        f.write("\n")

        # ----------------------------------------------------
        # NH-CONS
        # ----------------------------------------------------

        f.write(
            "=" * 60 + "\n"
        )

        f.write(
            "10% BELOW 52W HIGH & CONSOLIDATING\n"
        )

        f.write(
            "=" * 60 + "\n"
        )

        for row in near_high_results:

            f.write(
                f"{row[0]} | "
                f"Price:{row[1]} | "
                f"Change:{row[2]} | "
                f"Volume:{row[3]}\n"
            )

    print(
        f"\nCreated {WATCHLIST_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def run():

    print(
        "\n"
        + "=" * 80
    )

    print(
        "STARTING STOCK SCREENING"
    )

    print(
        "=" * 80
    )

    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=HEADLESS
        )

        page = browser.new_page(
            viewport={
                "width": 1920,
                "height": 1080
            }
        )

        # ----------------------------------------------------
        # Dashboard
        # ----------------------------------------------------

        widget_lists = scrape_dashboard(
            page
        )

        # ----------------------------------------------------
        # IB
        # ----------------------------------------------------

        ib_results = scrape_chartink_table(
            page,
            SCREENER_URL
        )

        # ----------------------------------------------------
        # EMA
        # ----------------------------------------------------

        ema_results = scrape_chartink_table(
            page,
            EMA_SCREENER_URL
        )

        # ----------------------------------------------------
        # CONS
        # ----------------------------------------------------

        consolidation_results = (
            scrape_chartink_table(
                page,
                CONSOLIDATION_SCREENER_URL
            )
        )

        # ----------------------------------------------------
        # NH-CONS
        # ----------------------------------------------------

        near_high_results = (
            scrape_chartink_table(
                page,
                NEAR_HIGH_CONSOLIDATION_URL
            )
        )

        # ----------------------------------------------------
        # Close browser
        # ----------------------------------------------------

        browser.close()

    print(
        "\nBrowser closed."
    )

    # ========================================================
    # IB HISTORY
    # ========================================================

    ib_history = update_ib_history(
        ib_results
    )

    # ========================================================
    # DASHBOARD RANKING
    # ========================================================

    ranked = rank_stocks(
        widget_lists
    )

    # Only stocks appearing in 2+ dashboard widgets
    ranked = [
        row
        for row in ranked
        if row[1] >= 2
    ]

    # ========================================================
    # SCREENER SETS
    # ========================================================

    ib_set = {
        row[0]
        for row in ib_results
    }

    ema_set = {
        row[0]
        for row in ema_results
    }

    cons_set = {
        row[0]
        for row in consolidation_results
    }

    nh_cons_set = {
        row[0]
        for row in near_high_results
    }

    # ========================================================
    # TOP PICKS
    # ========================================================

    combined = []

    for stock, count in ranked:

        tags = []

        if stock in ib_set:

            tags.append(
                "IB"
            )

        if stock in ema_set:

            tags.append(
                "EMA"
            )

        if stock in cons_set:

            tags.append(
                "CONS"
            )

        if stock in nh_cons_set:

            tags.append(
                "NH-CONS"
            )

        score = count * 10

        combined.append(
            (
                stock,
                count,
                score,
                "+".join(tags)
            )
        )

    combined.sort(
        key=lambda x: x[2],
        reverse=True
    )

    # --------------------------------------------------------
    # Top 5
    # --------------------------------------------------------

    top_picks = combined[:5]

    top_symbols = {
        row[0]
        for row in top_picks
    }

    # --------------------------------------------------------
    # Remaining dashboard stocks
    # --------------------------------------------------------

    remaining = [
        row
        for row in ranked
        if row[0] not in top_symbols
    ][:5]

    # ========================================================
    # SPECIAL IB → CONS WATCH
    # ========================================================

    ib_cons_watch = build_ib_cons_watch(
        consolidation_results,
        ib_history
    )

    # ========================================================
    # SCREENER DISPLAY RESULTS
    # ========================================================

    ib_final = prioritize_screener(
        ib_results,
        top_symbols,
        10
    )

    ema_final = prioritize_screener(
        ema_results,
        top_symbols,
        15
    )

    cons_final = sort_by_price(
        consolidation_results,
        15
    )

    nh_cons_final = sort_by_price(
        near_high_results,
        15
    )

    # ========================================================
    # TABLES
    # ========================================================

    ib_table = make_table(
        ib_final
    )

    ema_table = make_table(
        ema_final
    )

    cons_table = make_table(
        cons_final
    )

    nh_cons_table = make_table(
        nh_cons_final
    )

    # --------------------------------------------------------
    # Dashboard remaining table
    # --------------------------------------------------------

    if remaining:

        dashboard_table = tabulate(
            remaining,
            headers=[
                "Stock",
                "Count"
            ],
            tablefmt="github"
        )

    else:

        dashboard_table = (
            "No additional dashboard signals."
        )

    # --------------------------------------------------------
    # IB → CONS table
    # --------------------------------------------------------

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
    # TOP PICK TEXT
    # ========================================================

    if top_picks:

        top_text_lines = []

        for index, row in enumerate(
            top_picks,
            start=1
        ):

            stock = row[0]
            score = row[2]
            tags = row[3]

            line = (
                f"{index}. "
                f"<b>{stock}</b> | "
                f"Score: {score}"
            )

            if tags:

                line += (
                    f" | {tags}"
                )

            top_text_lines.append(
                line
            )

        top_text = "\n".join(
            top_text_lines
        )

    else:

        top_text = (
            "No strong picks."
        )

    # ========================================================
    # CREATE WATCHLIST FILE
    # ========================================================

    create_watchlist_file(
        top_picks,
        remaining,
        ib_results,
        ib_cons_watch,
        consolidation_results,
        ema_results,
        near_high_results
    )

    # ========================================================
    # TELEGRAM MESSAGE
    #
    # HTML is used instead of Markdown.
    # Tables are inside <pre>, avoiding Markdown parsing errors.
    # ========================================================

    message = (

        "<b>📊 STOCKS FOR THE DAY</b>\n\n"

        "🔥 <b>TOP PICKS</b>\n"
        f"{top_text}\n\n"

        "📊 <b>DASHBOARD - REMAINING SIGNALS</b>\n"
        "<pre>"
        f"{dashboard_table}"
        "</pre>\n\n"

        "⚡ <b>CLOSE ABOVE SUPERTREND &amp; NEAR 52W LOW</b>\n"
        "<pre>"
        f"{ib_table}"
        "</pre>\n\n"

        "🔥🔥🔥 <b>IB → CONS WATCH</b> 🔥🔥🔥\n"
        "<i>Appeared in IB during the last 5 trading days "
        "AND is in CONS today.</i>\n"
        "<i>IB shows the most recent IB appearance.</i>\n"
        "<pre>"
        f"{ib_cons_watch_table}"
        "</pre>\n\n"

        "⚡⚡ <b>SUPERTREND CONTRACTION "
        "SWING HIGH BREAKOUT WAIT</b>\n"
        "<pre>"
        f"{cons_table}"
        "</pre>\n\n"

        "⚡⚡⚡ <b>5% PRE-BREAKOUT</b>\n"
        "<pre>"
        f"{ema_table}"
        "</pre>\n\n"

        "🔥⚡ <b>10% BELOW 52W HIGH "
        "&amp; CONSOLIDATING</b>\n"
        "<pre>"
        f"{nh_cons_table}"
        "</pre>"
    )

    # ========================================================
    # SEND TELEGRAM
    #
    # EXACTLY ONE MESSAGE
    # EXACTLY ONE FILE
    # ========================================================

    print(
        "\nSending Telegram message..."
    )

    send_telegram_message(
        message
    )

    print(
        "\nSending watchlist file..."
    )

    send_telegram_file(
        WATCHLIST_FILE
    )

    # ========================================================
    # FINISHED
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )

    print(
        "SCREENING COMPLETED"
    )

    print(
        "=" * 80
    )

    print(
        f"IB stocks: {len(ib_results)}"
    )

    print(
        f"EMA stocks: {len(ema_results)}"
    )

    print(
        f"CONS stocks: "
        f"{len(consolidation_results)}"
    )

    print(
        f"NH-CONS stocks: "
        f"{len(near_high_results)}"
    )

    print(
        f"IB → CONS WATCH: "
        f"{len(ib_cons_watch)}"
    )

    print(
        f"IB history days stored: "
        f"{len(ib_history)}"
    )

    print(
        f"Watchlist file: "
        f"{WATCHLIST_FILE}"
    )

    print(
        "DONE."
    )


# ============================================================
# RUN ONCE
# ============================================================

if __name__ == "__main__":

    run()
