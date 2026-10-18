
from playwright.sync_api import sync_playwright
import json

URL = "https://getmarketstrength.com/#india/scans"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Capture JSON-like responses that may contain scan data.
    responses = []

    def capture_response(response):
        content_type = response.headers.get("content-type", "")
        if "json" in content_type.lower():
            responses.append({
                "url": response.url,
                "status": response.status,
                "content_type": content_type,
            })

    page.on("response", capture_response)

    try:
        response = page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(10000)

        report = {
            "http_status": response.status if response else None,
            "final_url": page.url,
            "title": page.title(),
            "body_text": page.locator("body").inner_text()[:15000],
            "html_tables": page.locator("table").count(),
            "table_rows": page.locator("table tr").count(),
            "links": page.locator("a").count(),
            "json_responses": responses,
        }

        with open(
            "getmarketstrength_test_report.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(json.dumps(report, indent=2, ensure_ascii=False))

        page.screenshot(
            path="getmarketstrength_test.png",
            full_page=True,
        )

    except Exception as exc:
        print(f"TEST FAILED: {type(exc).__name__}: {exc}")

    finally:
        browser.close()
