import sys
import time
from playwright.sync_api import sync_playwright

RUN_ID = "c3df7d37-6f22-4334-bd3c-bf9a07eee7b6"
URL = f"http://localhost:3000/workflow-runs/{RUN_ID}"

def run_test():
    print(f"Launching Playwright to test Refresh button on {URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # 1. Load the page initial state
        print("Navigating to page...")
        page.goto(URL, wait_until="networkidle")
        time.sleep(1)

        # Take before screenshot
        before_screenshot_path = "frontend/tests/e2e/refresh_before.png"
        page.screenshot(path=before_screenshot_path, full_page=True)
        print(f"Saved before screenshot: {before_screenshot_path}")

        # 2. Record requests fired by clicking Refresh
        requests_fired = []

        def on_request(request):
            url = request.url
            if "/api/" in url:
                requests_fired.append(url)

        page.on("request", on_request)

        # 3. Locate Refresh button
        refresh_btn = page.get_by_role("button", name="Refresh")
        assert refresh_btn.is_visible(), "Refresh button not visible on page!"

        print("Clicking Refresh button...")
        requests_fired.clear()
        refresh_btn.click()

        # Wait for network idle or requests to complete
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        after_screenshot_path = "frontend/tests/e2e/refresh_after.png"
        page.screenshot(path=after_screenshot_path, full_page=True)
        print(f"Saved after screenshot: {after_screenshot_path}")

        print(f"\n--- Requests fired by click ({len(requests_fired)}) ---")
        for req in requests_fired:
            print("  ->", req)

        # Check required endpoints
        required_endpoints = [
            f"/api/workflow-runs/{RUN_ID}",
            f"/api/workflow-runs/{RUN_ID}/draft",
            f"/api/workflow-runs/{RUN_ID}/research",
            f"/api/workflow-runs/{RUN_ID}/brief",
            f"/api/workflow-runs/{RUN_ID}/publication",
            "/media",
            "/analytics",
        ]

        missing = []
        for ep in required_endpoints:
            if not any(ep in req for req in requests_fired):
                missing.append(ep)

        print("\nVerification check:")
        print(f"  All required endpoints present: {len(missing) == 0} (Missing: {missing})")

        assert len(missing) == 0, f"Missing requested endpoints: {missing}"

        browser.close()
        print("\n✓ CP-1A.1 Real interaction test passed successfully!")

if __name__ == "__main__":
    run_test()
