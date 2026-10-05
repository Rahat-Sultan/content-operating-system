import time
from playwright.sync_api import sync_playwright

STRATEGIES_URL = "http://localhost:3000/strategies"

def test_voice_sample_ui():
    print("Launching Playwright to verify Voice / Style Sample UI...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # 1. Open Strategies page
        page.goto(STRATEGIES_URL, wait_until="networkidle")
        time.sleep(1)

        # 2. Click "New Strategy" button to open modal
        new_strat_btn = page.get_by_role("button", name="+ New Strategy")
        assert new_strat_btn.is_visible(), "New Strategy button not visible!"
        new_strat_btn.click()
        time.sleep(1)

        # Screenshot 1: Create Modal with voice sample textarea
        create_screenshot = "frontend/tests/e2e/voice_sample_create_modal.png"
        page.screenshot(path=create_screenshot)
        print(f"Saved: {create_screenshot}")

        # Fill in form with test strategy name and voice sample
        page.fill("input[placeholder*='Cloud Native Infrastructure']", "TEMP-UI-Voice-Strategy")
        voice_textarea = page.locator("textarea[placeholder*='how you or your team actually write']")
        assert voice_textarea.is_visible(), "Voice / Style Sample textarea not found in create modal!"

        test_sample_content = "This is a verified UI test voice sample string for CP-1B.5."
        voice_textarea.fill(test_sample_content)

        # Submit create form
        page.get_by_role("button", name="Create Strategy").click()
        time.sleep(2)
        page.wait_for_load_state("networkidle")

        # 3. Locate newly created strategy link and navigate to detail page
        strat_link = page.get_by_text("TEMP-UI-Voice-Strategy").first
        assert strat_link.is_visible(), "Newly created strategy not in list!"
        strat_link.click()
        time.sleep(1)
        page.wait_for_load_state("networkidle")

        # Screenshot 2: Strategy detail view showing saved voice sample
        detail_screenshot = "frontend/tests/e2e/voice_sample_detail_view.png"
        page.screenshot(path=detail_screenshot)
        print(f"Saved: {detail_screenshot}")

        body_text = page.locator("body").inner_text()
        assert test_sample_content in body_text, "Saved voice sample text not rendered on detail page!"

        # 4. Click "Edit Configuration"
        edit_btn = page.get_by_role("button", name="Edit Configuration")
        assert edit_btn.is_visible(), "Edit Configuration button not visible!"
        edit_btn.click()
        time.sleep(1)

        # Screenshot 3: Strategy Edit form showing loaded voice sample
        edit_screenshot = "frontend/tests/e2e/voice_sample_edit_form.png"
        page.screenshot(path=edit_screenshot)
        print(f"Saved: {edit_screenshot}")

        edit_textarea = page.locator("textarea[placeholder*='how you or your team actually write']")
        assert edit_textarea.is_visible(), "Voice sample textarea not visible in edit form!"
        current_val = edit_textarea.input_value()
        assert current_val == test_sample_content, f"Voice sample textarea did not load saved value, got '{current_val}'"

        # Update voice sample
        updated_sample = test_sample_content + " (Updated in edit form)"
        edit_textarea.fill(updated_sample)
        page.get_by_role("button", name="Save Changes").click()
        time.sleep(2)
        page.wait_for_load_state("networkidle")

        # Screenshot 4: Strategy detail after edit save
        updated_screenshot = "frontend/tests/e2e/voice_sample_updated_view.png"
        page.screenshot(path=updated_screenshot)
        print(f"Saved: {updated_screenshot}")

        body_text_updated = page.locator("body").inner_text()
        assert updated_sample in body_text_updated, "Updated voice sample text not rendered on detail page!"

        print("\n✓ CP-1B.5 UI Voice Sample test passed successfully!")
        browser.close()

if __name__ == "__main__":
    test_voice_sample_ui()
