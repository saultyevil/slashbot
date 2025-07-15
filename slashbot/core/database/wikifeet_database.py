import datetime
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from slashbot.core.database.models import WikiFeetModel, WikiFeetPicture, WikiFeetSqlBase
from slashbot.core.logger import Logger


class WikiFeetScraper(Logger):
    """A class for scraping a model's best pictures from Wikifeet."""

    def __init__(
        self,
    ) -> None:
        """Initialise the WikiFeetScraper class."""
        super().__init__()

        options = webdriver.FirefoxOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

        self.base_url = "https://wikifeet.com"
        if Path("/usr/local/bin/geckodriver").exists():
            service = Service("/usr/local/bin/geckodriver")
            self.driver = webdriver.Firefox(options=options, service=service)
        else:
            self.driver = webdriver.Firefox(options=options)
        self.wait = WebDriverWait(self.driver, timeout=10)

    def __del__(self) -> None:
        """Ensure the browser is closed when the object is destroyed."""
        if hasattr(self, "driver"):
            self.driver.quit()

    @staticmethod
    def make_url_model_name(name: str) -> str:
        """Convert a model's name to the WikiFeet URL format.

        Parameters
        ----------
        name : str
            The name of the model.

        Returns
        -------
        str
            The formatted model name for the URL.

        """
        return "_".join(part.capitalize() for part in name.split())

    @staticmethod
    def _get_model_data(html: str) -> dict:
        """Extract model data from the WikiFeet HTML.

        Parameters
        ----------
        html : str
            The HTML content of the WikiFeet model page.

        Returns
        -------
        dict
            A dictionary containing the model data.

        """
        json_symbol = "tdata = "
        start_index = html.find(json_symbol)
        if start_index == -1:
            msg = "Could not find model data in HTML"
            raise ValueError(msg)

        start_index = start_index + len(json_symbol) - 1
        end_index = html.find("\n", start_index) - 1
        actress_json_data_string = html[start_index:end_index]

        return json.loads(actress_json_data_string)

    async def get_model_info(self, model_name: str) -> WikiFeetModel:
        """Get metadata info about a model.

        Parameters
        ----------
        model_name : str
            The name of the model.

        Returns
        -------
        WikiFeetModel
            The info the model in a WikiFeetModel object.

        """
        model_url = self.make_url_model_name(model_name)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(f"https://wikifeet.com/{model_url}")
                response.raise_for_status()
            except httpx.HTTPError as e:
                exc_msg = f"Unable to get webpage for {model_name}: {e}"
                self.log_error("%s", exc_msg)
                raise ValueError(exc_msg) from e

        try:
            data = self._get_model_data(response.text)
        except (ValueError, json.JSONDecodeError) as e:
            exc_msg = f"Unable to parse model data for {model_name}: {e}"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg) from e

        now = datetime.datetime.now(tz=datetime.UTC)

        try:
            birthday = datetime.datetime.fromisoformat(data["bdate"].replace("Z", "+00:00"))
            age = now.year - birthday.year - ((now.month, now.day) < (birthday.month, birthday.day))

            height_feet = float(data["height_us"][0])
            height_inches = float(data["height_us"][1:])
            height_cm = height_feet * 30.48 + height_inches * 2.54
        except (KeyError, ValueError, IndexError) as e:
            exc_msg = f"Error parsing model data for {model_name}: {e}"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg) from e

        return WikiFeetModel(
            name=data["cname"],
            last_updated=now,
            foot_score=data["score"],
            shoe_size=data["ssize"],
            height_cm=height_cm,
            age=age,
            nationality=data["edata"]["nationality"],
        )

    def _handle_cookie_banner(self, timeout: int = 5) -> None:
        """Clicks the 'decline' button on a cookie banner.

        It waits for a short period for the banner to appear. If it's not
        found, it assumes one doesn't exist and continues without error.

        Parameters
        ----------
        timeout : int, optional
            The maximum time in seconds to wait for the banner, by default 5.

        """
        try:
            decline_button = WebDriverWait(self.driver, timeout).until(
                expected_conditions.element_to_be_clickable((By.CLASS_NAME, "cc-nb-reject"))
            )
            decline_button.click()
        except TimeoutException:
            # No banner was found, which is fine.
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

    def get_best_images_for_model(self, model_name_url: str) -> list[str]:
        """Get a sorted by best list of picture ids for the model.

        Parameters
        ----------
        model_name_url : str
            The URL name for the model to get the best images of.

        Returns
        -------
        list[str]
            The list of picture ids.

        """
        self.driver.get(f"{self.base_url}/{model_name_url}")

        self._handle_cookie_banner()

        # Sort images by "best" by clicking the filter buttons
        self._scroll_and_click(By.CSS_SELECTOR, "div.latest")
        self._scroll_and_click(By.XPATH, "//div[contains(text(), 'Best')]")

        # Wait for the sorted pictures to be present in the DOM
        self.wait.until(lambda driver: driver.find_element(By.XPATH, "//div[starts-with(@id, 'pid_')]"))

        # Find all picture elements and extract their IDs
        picture_elements = self.driver.find_elements(By.XPATH, "//div[starts-with(@id, 'pid_')]")
        picture_ids = [elem.get_attribute("id") for elem in picture_elements]

        # Clean up the IDs and return the list
        # (e.g., transforms "pid_12345" into "12345")
        return [pid.split("_")[-1] for pid in picture_ids if pid]


class WikiFeetDatabase(Logger):
    """A class to interact with the WikiFeet database."""

    def __init__(self, database_url: str, scraper: WikiFeetScraper) -> None:
        """Initialize the WikiFeetDatabase with a database URL.

        Parameters
        ----------
        database_url : str
            The database connection URL.
        scraper : WikiFeetScraper
            A WikiFeet scraper instance.

        """
        super().__init__(prepend_msg="[WikiFeetDatabase]")
        self.engine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.scraper = scraper

    async def init_database(self) -> None:
        """Initialize the database and create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(WikiFeetSqlBase.metadata.create_all)

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Asynchronous context manager for database session.

        Returns
        -------
        AsyncGenerator[AsyncSession, None]
            An async generator yielding an AsyncSession.

        """
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def add_model(self, model: WikiFeetModel) -> WikiFeetModel:
        """Add a WikiFeetModel instance to the database.

        Parameters
        ----------
        model : WikiFeetModel
            The model instance to add.

        Returns
        -------
        WikiFeetModel
            The added model (with ID populated).

        Raises
        ------
        ValueError
            If the model already exists in the database.

        """
        async with self.get_session() as session:
            try:
                session.add(model)
                await session.commit()
                await session.refresh(model)
                return model
            except IntegrityError as e:
                await session.rollback()
                exc_msg = f"Model {model.name} already exists in database"
                self.log_error("%s", exc_msg)
                raise ValueError(exc_msg) from e

    async def add_picture(self, picture: WikiFeetPicture) -> None:
        """Add a WikiFeetPicture instance to the database.

        Parameters
        ----------
        picture : WikiFeetPicture
            The picture instance to add.

        Raises
        ------
        ValueError
            If the picture already exists in the database.

        """
        async with self.get_session() as session:
            try:
                session.add(picture)
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                exc_msg = f"Picture {picture.picture_id} already exists in database"
                self.log_error("%s", exc_msg)
                raise ValueError(exc_msg) from e

    async def get_model(self, model_name: str) -> WikiFeetModel | None:
        """Retrieve a WikiFeetModel by name.

        Parameters
        ----------
        model_name : str
            The name of the model to retrieve.

        Returns
        -------
        WikiFeetModel or None
            The model instance if found, otherwise None.

        """
        async with self.get_session() as session:
            query = select(WikiFeetModel).where(WikiFeetModel.name == model_name)
            result = await session.execute(query)
            model = result.scalar_one_or_none()

            if model:
                # Refresh the model to ensure it's not stale
                await session.refresh(model)
                return model

            return None

    async def get_or_create_model(self, model_name: str) -> WikiFeetModel:
        """Get an existing model or create a new one.

        Parameters
        ----------
        model_name : str
            The name of the model to retrieve or create.

        Returns
        -------
        WikiFeetModel
            The model instance.

        """
        # First try to get existing model
        model = await self.get_model(model_name)
        if model:
            return model

        # Model doesn't exist, create it
        try:
            model_info = await self.scraper.get_model_info(model_name)
            model = await self.add_model(model_info)
            await self.update_model_pictures(model_name, model.id)

            return model
        except ValueError as e:
            # If model was created by another process in the meantime, get it
            if "already exists" in str(e):
                model = await self.get_model(model_name)
                if model:
                    return model
            raise

    async def get_model_pictures(self, model_name: str) -> list[WikiFeetPicture]:
        """Retrieve a model's pictures.

        Parameters
        ----------
        model_name : str
            The name of the model.

        Returns
        -------
        list[WikiFeetPicture]
            A list containing WikiFeetPicture objects.

        """
        model = await self.get_or_create_model(model_name)

        async with self.get_session() as session:
            stmt = (
                select(WikiFeetModel).options(selectinload(WikiFeetModel.pictures)).where(WikiFeetModel.id == model.id)
            )
            result = await session.execute(stmt)
            model_with_pictures = result.scalar_one_or_none()

        return model_with_pictures.pictures if model_with_pictures else []

    async def update_model_pictures(self, model_name: str, model_id: int) -> None:
        """Update the pictures for a model.

        Parameters
        ----------
        model_name : str
            The name of the model.
        model_id : int
            The database ID of the model.

        """
        ids_best_pictures = self.scraper.get_best_images_for_model(self.scraper.make_url_model_name(model_name))

        for pid in ids_best_pictures:
            try:
                await self.add_picture(WikiFeetPicture(model_id=model_id, picture_id=pid))
            except ValueError:
                continue
