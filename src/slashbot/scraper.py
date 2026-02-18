import atexit
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from slashbot.logger import Logger


class FirefoxWebScraper(Logger):
    """A class for scraping web content using Firefox."""

    def __init__(self, log_label: str = "[FirefoxWebScraper]") -> None:
        """Initialise the scraper class.

        Parameters
        ----------
        log_label : str
            The label to use for log entries.

        """
        super().__init__(prepend_msg=log_label)

        options = webdriver.FirefoxOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

        if Path("/usr/local/bin/geckodriver").exists():
            service = Service("/usr/local/bin/geckodriver")
            self.driver = webdriver.Firefox(options=options, service=service)
        else:
            self.driver = webdriver.Firefox(options=options)

        self.driver.install_addon("data/uBlock.firefox.xpi", temporary=True)
        self.wait = WebDriverWait(self.driver, timeout=20)
        atexit.register(self._cleanup_after)

    def __del__(self) -> None:
        """Ensure the browser is closed when the object is destroyed."""
        self.driver.quit()

    def _cleanup_after(self) -> None:
        """Ensure the browser is closed at exit."""
        self.driver.quit()

    def _handle_cookie_banner(self, timeout: int = 1) -> None:
        """Clicks the 'decline' button on a cookie banner.

        It waits for a short period for the banner to appear. If it's not
        found, it assumes one doesn't exist and continues without error.

        Parameters
        ----------
        timeout : int, optional
            The maximum time in seconds to wait for the banner, by default 2.

        """
        try:
            decline_button = WebDriverWait(self.driver, timeout).until(
                expected_conditions.element_to_be_clickable((By.CLASS_NAME, "cc-nb-reject"))
            )
            decline_button.click()
        except TimeoutException:
            pass

    def _scroll_and_click(self, by: str, value: str) -> None:
        """Scrolls to an element and clicks it.

        This function waits for an element to be present, scrolls it into
        view, waits until it's clickable, and then performs a click.

        Parameters
        ----------
        by : By
            The Selenium locator strategy (e.g., By.CSS_SELECTOR).
        value : str
            The locator value for the element.

        """
        # First, find the element and scroll it into view
        element = self.wait.until(
            expected_conditions.presence_of_element_located((by, value)),
        )
        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)

        # Now, wait for the element to be clickable and click it
        clickable_element = self.wait.until(
            expected_conditions.element_to_be_clickable((by, value)),
        )
        clickable_element.click()
