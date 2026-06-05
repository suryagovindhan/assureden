from playwright.sync_api import sync_playwright
import json
import sys
import os

# Add parent directory to path so agent.domains works
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from agent.domains import pam_operations, iam_operations

class AgentExecutor:
    def __init__(self):
        pass

    def parse_and_execute(self, instruction_json: str):
        try:
            instruction = json.loads(instruction_json)
        except json.JSONDecodeError:
            return {"status": "ERROR", "error": "Invalid JSON payload"}

        domain = instruction.get("domain", "").upper()
        action = instruction.get("action", "")
        target_url = instruction.get("target_url", "")

        # Optional: check if bundled Chromium path exists
        # executable_path = "bin/chrome.exe"
        # headless = True

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            result = {"status": "ERROR", "error": f"Unknown domain {domain} or action {action}"}

            try:
                if domain == "PAM":
                    if action == "test-vaulting":
                        result = pam_operations.execute_vaulting_test(page, target_url)
                    elif action == "test-checkout":
                        result = pam_operations.execute_credential_checkout(page, target_url)
                elif domain == "IAM":
                    if action == "test-provisioning":
                        result = iam_operations.execute_provisioning_test(page, target_url)
                    elif action == "test-sso":
                        result = iam_operations.execute_sso_test(page, target_url)
            except Exception as e:
                result = {"status": "ERROR", "error": str(e)}
            finally:
                browser.close()

            return result
