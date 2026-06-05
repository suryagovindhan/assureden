from playwright.sync_api import Page

class CommonElements:
    def __init__(self, page: Page):
        self.page = page

    def click_button(self, text: str):
        self.page.get_by_role("button", name=text).click()

    def fill_input(self, label: str, value: str):
        self.page.get_by_label(label).fill(value)
