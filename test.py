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
HEADLESS = True

# ==========================================

# TELEGRAM

# ==========================================

def send_to_telegram(message):
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

```
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
```

# ==========================================

# HELPER (ONLY ADDITION)

# ==========================================

def parse_price(p):
try:
return float(p.replace(",", "").strip())
except:
return 0.0

# ==========================================

# DASHBOARD SCRAPER

# ==========================================

def scrape_dashboard(page):
widget_results = []

```
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
```

# ==========================================

# SCREENER SCRAPER

# ==========================================

def scrape_screener(page):
results = []

```
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
    price = cols[3].inner_text().strip()
    change = cols[4].inner_text().strip()

    volume_text = cols[5].inner_text().strip()
    volume = int(volume_text.replace(",", "")) if volume_text else 0

    results.append([symbol, price, change, volume])

return results
```

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

````
    widget_lists = scrape_dashboard(page)

    if not widget_lists:
        send_to_telegram("❌ No dashboard data.")
        return

    ranked = rank_stocks(widget_lists)

    screener_results = scrape_screener(page)
    screener_set = {s[0] for s in screener_results}

    browser.close()

# FILTER
ranked = [r for r in ranked if r[1] >= 2]

# FULL SCORING
combined = []
for stock, count in ranked:
    score = count * 10
    tag = "IB" if stock in screener_set else ""
    combined.append((stock, count, score, tag))

combined = sorted(combined, key=lambda x: x[2], reverse=True)

# TOP PICKS
top_picks = combined[:15]
top_symbols = {s[0] for s in top_picks}

top_text = "\n".join([
    f"{i+1}. {s[0]} | Score:{s[2]} {s[3]}"
    for i, s in enumerate(top_picks)
]) if top_picks else "No strong picks."

# DASHBOARD
remaining = [r for r in ranked if r[0] not in top_symbols][:30]

df = pd.DataFrame(remaining, columns=["Stock", "Count"])
df["Strength"] = df["Count"].apply(lambda x: "🔥" if x >= 3 else "⚡")

dashboard_table = tabulate(df, headers="keys", tablefmt="github", showindex=False)

# ==========================================
# SORT SCREENER (LOW → HIGH PRICE)
# ==========================================
screener_results_sorted = sorted(
    screener_results,
    key=lambda x: parse_price(x[1])
)

# SCREENER TABLE
screener_table = tabulate(
    screener_results_sorted[:20],
    headers=["Stock", "Price", "%Change", "Volume"],
    tablefmt="github"
)

# FINAL MESSAGE
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

    "🔹 Inside Bar Screener (Low → High Price)\n"
    "```\n"
    f"{screener_table}\n"
    "```"
)

if len(message) > 4000:
    message = message[:4000]

print(message)
send_to_telegram(message)
````

if **name** == "**main**":
run()
