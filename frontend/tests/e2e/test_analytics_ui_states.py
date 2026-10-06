"""
Analytics status UI (CP-D.1 to CP-D.5, CP-C.4).

Real page: the live run c3df7d37-... (no mocks), screenshot + assertions.
Mocked pages: the publication and analytics responses are replaced so each
state is shown exactly, one state per screenshot.

Run with the backend on :8000 and the frontend on :3000.
"""
import copy
import json
import os
from playwright.sync_api import sync_playwright

RUN_ID = "c3df7d37-6f22-4334-bd3c-bf9a07eee7b6"
PUB_ID = "a95b9eec-4d6f-4e25-b5da-d5100cfa11cc"
URL = f"http://localhost:3000/workflow-runs/{RUN_ID}"
SHOTS = os.path.join(os.path.dirname(__file__), "analytics_states")
API_PUB = f"**/api/workflow-runs/{RUN_ID}/publication"
API_ANALYTICS = f"**/api/publications/{PUB_ID}/analytics"

BASE_STATUS = {
    "state": "none",
    "last_attempt_at": None,
    "last_attempt_outcome": None,
    "last_attempt_source": None,
    "last_attempt_message": None,
    "last_attempt_technical": None,
    "last_buffer_response_at": None,
    "attempt_number": 1,
    "network_failures_in_row": 0,
    "network_retry_paused": False,
    "next_sync_at": None,
    "next_sync_overdue": False,
    "scheduler_running": True,
    "valid_snapshot": None,
}

REAL_BUFFER_SNAPSHOT = {
    "id": "00000000-0000-0000-0000-000000000001",
    "publication_id": PUB_ID,
    "collected_at": "2026-10-06T10:32:58+05:00",
    "metrics": {
        "impressions": 95, "reactions": 2, "likes": 2, "comments": 0, "shares": 0, "clicks": 0,
        "provider": "buffer", "is_stub": False, "is_initial": False,
    },
}


def _status(**overrides):
    status = copy.deepcopy(BASE_STATUS)
    status.update(overrides)
    return status


def _with_status(page, status: dict, snapshots: list | None = None):
    """Serves the real publication response with analytics_status replaced, and optionally the snapshot list."""
    def handle_pub(route):
        response = route.fetch()
        body = response.json()
        body["analytics_status"] = status
        body["schedule_info"]["scheduler_running"] = status["scheduler_running"]
        route.fulfill(response=response, json=body)

    def handle_analytics(route):
        if snapshots is None:
            route.continue_()
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(snapshots))

    page.unroute(API_PUB)
    page.unroute(API_ANALYTICS)
    page.route(API_PUB, handle_pub)
    page.route(API_ANALYTICS, handle_analytics)


def _status_block(page):
    block = page.locator("[data-testid='analytics-status']")
    block.wait_for(state="visible", timeout=15000)
    return block


def test_real_page_shows_network_error_honestly():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(URL, wait_until="networkidle")
        block = _status_block(page)
        assert block.get_attribute("data-state") == "network_error", block.get_attribute("data-state")
        text = block.inner_text()
        assert "Couldn't reach Buffer from this server" in text, text
        # The live worker is not running and the sync is in the past.
        assert "Automatic sync is OFF" in text, text
        assert "Overdue since" in page.locator("[data-testid='analytics-next-sync']").inner_text()
        page.locator("[data-testid='analytics-status']").screenshot(path=os.path.join(SHOTS, "real_run_network_error.png"))
        browser.close()


def test_each_state_is_shown_once_with_its_own_text():
    cases = {
        "not_collected_yet": _status(
            state="not_collected_yet",
            last_attempt_at="2026-10-06T09:00:00+05:00", last_attempt_outcome="not_ready",
            last_buffer_response_at="2026-10-06T09:00:00+05:00",
            next_sync_at="2026-10-06T13:00:00+05:00", attempt_number=2,
        ),
        "failed": _status(
            state="failed", last_attempt_at="2026-10-06T09:00:00+05:00", last_attempt_outcome="failed",
            last_attempt_message="Buffer authentication failed (HTTP 401)",
        ),
        "manual": _status(
            state="manual", last_attempt_at="2026-10-05T09:00:00+05:00", last_attempt_outcome="ready",
            last_buffer_response_at="2026-10-05T09:00:00+05:00",
        ),
    }
    snapshots_for = {"manual": [{**REAL_BUFFER_SNAPSHOT, "metrics": {**REAL_BUFFER_SNAPSHOT["metrics"], "provider": "manual"}}]}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        for name, status in cases.items():
            _with_status(page, status, snapshots=snapshots_for.get(name, []))
            page.goto(URL, wait_until="networkidle")
            block = _status_block(page)
            assert block.get_attribute("data-state") == name, (name, block.get_attribute("data-state"))
            block.screenshot(path=os.path.join(SHOTS, f"state_{name}.png"))
        browser.close()


def test_overdue_and_scheduler_off_wording():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _with_status(page, _status(
            state="none", scheduler_running=False,
            next_sync_at="2026-10-05T13:39:00+05:00", next_sync_overdue=True, attempt_number=2,
        ))
        page.goto(URL, wait_until="networkidle")
        block = _status_block(page)
        text = block.inner_text()
        assert "Automatic sync is OFF" in text, text
        assert "python -m app.scheduler" in text, text
        assert "Overdue since" in text, text
        assert "Attempt 2 of 6" in text, text
        block.screenshot(path=os.path.join(SHOTS, "state_overdue_scheduler_off.png"))
        browser.close()


def test_headline_is_dash_not_zero_without_a_valid_snapshot():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _with_status(page, _status(state="network_error"), snapshots=[])
        page.goto(URL, wait_until="networkidle")
        block = _status_block(page)
        assert block.get_attribute("data-state") == "network_error"
        # The headline cards sit just above the status block.
        cards = page.locator("text=Impressions").locator("xpath=following-sibling::span[1]").first
        assert cards.inner_text().strip() == "—", cards.inner_text()
        browser.close()


def test_stub_and_quarantined_rows_hidden_by_default():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        stub = {**REAL_BUFFER_SNAPSHOT, "id": "00000000-0000-0000-0000-000000000002",
                "metrics": {"impressions": 3110, "is_stub": True, "provider": "stub"}}
        quarantined = {**REAL_BUFFER_SNAPSHOT, "id": "00000000-0000-0000-0000-000000000003",
                       "metrics": {"impressions": 0, "reactions": 0, "invalid_reason": "uncollected_buffer_placeholder",
                                   "provider": "buffer", "is_stub": False}}
        _with_status(page, _status(state="available", valid_snapshot={"id": REAL_BUFFER_SNAPSHOT["id"], "collected_at": REAL_BUFFER_SNAPSHOT["collected_at"], "provider": "buffer"}),
                     snapshots=[REAL_BUFFER_SNAPSHOT, stub, quarantined])
        page.goto(URL, wait_until="networkidle")
        page.get_by_text("Historical Snapshots").first.wait_for(timeout=15000)
        toggle = page.get_by_text("Show test / invalid rows (2)")
        assert toggle.is_visible(), "toggle missing"
        rows_before = page.locator("table tbody tr").count()
        toggle.click()
        rows_after = page.locator("table tbody tr").count()
        assert rows_after == rows_before + 2, (rows_before, rows_after)
        browser.close()


if __name__ == "__main__":
    os.makedirs(SHOTS, exist_ok=True)
    for test in [
        test_real_page_shows_network_error_honestly,
        test_each_state_is_shown_once_with_its_own_text,
        test_overdue_and_scheduler_off_wording,
        test_headline_is_dash_not_zero_without_a_valid_snapshot,
        test_stub_and_quarantined_rows_hidden_by_default,
    ]:
        test()
        print("PASS", test.__name__)
