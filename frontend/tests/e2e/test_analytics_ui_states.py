import time
import json
from playwright.sync_api import sync_playwright

RUN_ID = "c3df7d37-6f22-4334-bd3c-bf9a07eee7b6"
URL = f"http://localhost:3000/workflow-runs/{RUN_ID}"

def test_analytics_ui_states():
    print("Launching Playwright to verify Analytics UI states (CP-1C.3)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # --- STATE 1: Metrics Available ---
        print("\n--- Testing State 1: Metrics Available ---")
        page.goto(URL, wait_until="networkidle")
        time.sleep(1)

        # Confirm metrics summary card is visible
        impressions_card = page.get_by_text("Impressions").first
        assert impressions_card.is_visible(), "Metrics summary card not visible!"

        state1_screenshot = "frontend/tests/e2e/analytics_state1_available.png"
        page.screenshot(path=state1_screenshot)
        print(f"Saved: {state1_screenshot}")

        # --- STATE 2: Amber 'Not Yet Available' (409) ---
        print("\n--- Testing State 2: Amber 'Not Yet Available' (409) ---")
        # Intercept POST to /analytics/sync with 409
        def mock_409(route):
            if "analytics/sync" in route.request.url and route.request.method == "POST":
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps({"detail": "Metrics not yet available: Buffer is still indexing this post. Please try again shortly."})
                )
            else:
                route.continue_()

        page.route("**/analytics/sync", mock_409)

        sync_btn = page.get_by_role("button", name="Sync Metrics")
        assert sync_btn.is_visible(), "Sync Metrics button not visible!"
        sync_btn.click()
        time.sleep(1)
        page.wait_for_load_state("networkidle")

        amber_banner = page.locator("text=Metrics not yet available")
        assert amber_banner.is_visible(), "Amber 'not yet available' banner not visible!"

        state2_screenshot = "frontend/tests/e2e/analytics_state2_not_ready.png"
        page.screenshot(path=state2_screenshot)
        print(f"Saved: {state2_screenshot}")

        # Unroute 409
        page.unroute("**/analytics/sync")

        # --- STATE 3: Permanent Not Found (404) ---
        print("\n--- Testing State 3: Permanent Not Found (404) ---")
        def mock_404(route):
            if "analytics/sync" in route.request.url and route.request.method == "POST":
                route.fulfill(
                    status=404,
                    content_type="application/json",
                    body=json.dumps({"detail": "Post not found on analytics provider (permanent 404): Post not found on Buffer."})
                )
            else:
                route.continue_()

        page.route("**/analytics/sync", mock_404)

        sync_btn.click()
        time.sleep(1)
        page.wait_for_load_state("networkidle")

        not_found_banner = page.locator("text=Permanent Error: Post not found on provider")
        assert not_found_banner.is_visible(), "Permanent not found error banner not visible!"

        state3_screenshot = "frontend/tests/e2e/analytics_state3_permanent_not_found.png"
        page.screenshot(path=state3_screenshot)
        print(f"Saved: {state3_screenshot}")

        browser.close()
        print("\n✓ CP-1C.3 UI states in a real browser passed successfully!")

if __name__ == "__main__":
    test_analytics_ui_states()
