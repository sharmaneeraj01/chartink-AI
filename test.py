import time
from collections import Counter
import pandas as pd
from playwright.sync_api import sync_playwright

# ==========================================
# CONFIG
# ==========================================
DASHBOARD_URL = "https://chartink.com/dashboard/334725"
HEADLESS = True


# ==========================================
# SCRAPER ENGINE (STABLE VERSION)
# ==========================================
def scrape_chartink_dashboard(url):
    widget_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()

        print("Opening dashboard...")
        page.goto(url)

        # Wait for page load + JS rendering
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)

        # Scroll to load all widgets
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(3000)

        # Get all tables (each widget = table)
        tables = page.query_selector_all("table")

        print(f"Tables found: {len(tables)}")

        for i, table in enumerate(tables):
            stocks = table.query_selector_all("a")

            symbols = []
            for s in stocks:
                text = s.inner_text().strip()

                # Filter valid stock symbols
                if text.isupper() and 2 <= len(text) <= 15:
                    symbols.append(text)

            symbols = list(set(symbols))

            if symbols:
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

    # Keep stocks appearing in >= min_count widgets
    common = [stock for stock, count in counter.items() if count >= min_count]

    return common


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
from tabulate import tabulate

def save_results(common, ranked):
    # Filter strong signals
    ranked = [r for r in ranked if r[1] >= 2]

    print("\n📊 HIGH CONVICTION STOCKS (>=2 scanners)\n")

    if not ranked:
        print("No strong signals found.")
        return

    # Create DataFrame
    df = pd.DataFrame(ranked, columns=["Stock", "Scanner Count"])

    # Add strength label
    df["Strength"] = df["Scanner Count"].apply(
        lambda x: "🔥 Strong" if x >= 3 else "⚡ Medium"
    )

    # Sort
    df = df.sort_values(by="Scanner Count", ascending=False)

    # Pretty print table
    print(tabulate(df, headers="keys", tablefmt="fancy_grid", showindex=False))

    # Save
    df.to_csv("filtered_stocks.csv", index=False)

    print("\n✅ Saved: filtered_stocks.csv")
# ==========================================
# MAIN PIPELINE
# ==========================================
def run():
    widget_lists = scrape_chartink_dashboard(DASHBOARD_URL)

    if not widget_lists:
        print("❌ No data extracted.")
        return

    common = get_common_stocks(widget_lists)
    ranked = rank_stocks(widget_lists)

    save_results(common, ranked)


if __name__ == "__main__":
    run()