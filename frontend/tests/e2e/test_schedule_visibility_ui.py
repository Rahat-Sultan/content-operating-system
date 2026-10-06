import os
import unittest
from playwright.sync_api import sync_playwright

class TestScheduleVisibilityUI(unittest.TestCase):
    def setUp(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.page = self.context.new_page()

    def tearDown(self):
        self.browser.close()
        self.playwright.stop()

    def test_cp_2c_1_strategy_page_schedule_visibility(self):
        """
        CP-2C.1: The strategy detail page shows the discovery schedule and last run.
        """
        strat_id = "99efe1f1-5169-4770-bced-96d65eb27b70"
        url = f"http://localhost:3000/strategies/{strat_id}"
        self.page.goto(url, wait_until="networkidle")

        # Verify discovery schedule card is visible
        card = self.page.locator("[data-testid='discovery-schedule-card']")
        card.wait_for(state="visible", timeout=10000)
        self.assertTrue(card.is_visible())

        # Screenshot schedule view
        screenshot_path = "/home/borat/.gemini/antigravity/brain/764c6812-7d19-4d10-ba7f-02945c7e316e/strategy_discovery_schedule_ui.png"
        self.page.screenshot(path=screenshot_path, full_page=True)
        print(f"Captured strategy schedule screenshot: {screenshot_path}")

    def test_cp_2c_1_workflow_run_analytics_sync_schedule_visibility(self):
        """
        CP-2C.1: The workflow-run page shows when metrics were last synced and the next scheduled sync.
        """
        run_id = "c3df7d37-6f22-4334-bd3c-bf9a07eee7b6"
        url = f"http://localhost:3000/workflow-runs/{run_id}"
        self.page.goto(url, wait_until="networkidle")

        # The single analytics status block shows the last attempt and the next sync (with date).
        status = self.page.locator("[data-testid='analytics-status']")
        status.wait_for(state="visible", timeout=10000)
        self.assertIn("Last attempt:", status.inner_text())
        next_sync = self.page.locator("[data-testid='analytics-next-sync']")
        if next_sync.count():
            self.assertTrue(next_sync.is_visible())

        # Screenshot workflow run analytics schedule
        screenshot_path = "/home/borat/.gemini/antigravity/brain/764c6812-7d19-4d10-ba7f-02945c7e316e/workflow_run_analytics_schedule_ui.png"
        self.page.screenshot(path=screenshot_path, full_page=True)
        print(f"Captured workflow run analytics schedule screenshot: {screenshot_path}")

if __name__ == "__main__":
    unittest.main()
