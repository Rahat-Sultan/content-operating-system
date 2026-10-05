import os
import time
from dotenv import load_dotenv

# Ensure backend .env is loaded
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../backend/.env"))

from playwright.sync_api import sync_playwright
from app.db import SessionLocal
from app.analytics.models import Analytics
from app.publishing.models import Publication
from app.workflows.models import WorkflowRun

RUN_ID = "c3df7d37-6f22-4334-bd3c-bf9a07eee7b6"
URL = f"http://localhost:3000/workflow-runs/{RUN_ID}"

def run_test():
    db = SessionLocal()
    # Find publication for run
    run = db.query(WorkflowRun).filter(WorkflowRun.id == RUN_ID).first()
    pub = (
        db.query(Publication)
        .filter(Publication.content_version_id != None)
        .filter(Publication.external_id == "6ac3541363761da98b71e85b")
        .first()
    )
    assert pub, "Publication not found for run"

    print("Launching Playwright to test live data update on Refresh click...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        print("Navigating to page...")
        page.goto(URL, wait_until="networkidle")
        time.sleep(1)

        # Confirm initial metrics display
        initial_text = page.locator("body").inner_text()

        # Insert a distinctive snapshot into PostgreSQL
        # e.g. metrics with impressions = 99999
        test_impressions = 99999
        new_snapshot = Analytics(
            publication_id=pub.id,
            metrics={
                "impressions": test_impressions,
                "likes": 888,
                "comments": 77,
                "shares": 6,
                "clicks": 55,
                "engagement_rate": 0.05,
                "is_initial": False,
            },
        )
        db.add(new_snapshot)
        db.commit()
        db.refresh(new_snapshot)
        snapshot_id = new_snapshot.id
        print(f"Inserted test analytics snapshot {snapshot_id} with {test_impressions} impressions into DB.")

        try:
            # Click Refresh button without page reload
            refresh_btn = page.get_by_role("button", name="Refresh")
            print("Clicking Refresh button...")
            refresh_btn.click()

            page.wait_for_load_state("networkidle")
            time.sleep(2)

            page.screenshot(path="frontend/tests/e2e/refresh_live_update.png", full_page=True)

            updated_text = page.locator("body").inner_text()
            print(f"Checking if {test_impressions} or formatted 99,999 appears in UI...")
            has_update = "99,999" in updated_text or "99999" in updated_text

            print(f"Data actually updated in UI without page reload: {has_update}")
            assert has_update, f"Expected {test_impressions} to appear in UI after clicking Refresh!"
            print("✓ CP-1A.2 Data actually updates test passed successfully!")

        finally:
            # Clean up test snapshot from DB
            db.delete(new_snapshot)
            db.commit()
            print("Cleaned up test analytics snapshot from DB.")
            browser.close()

    db.close()

if __name__ == "__main__":
    run_test()
