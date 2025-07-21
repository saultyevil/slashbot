import asyncio
import datetime
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

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

from slashbot.core.database.models import WikiFeetComment, WikiFeetModel, WikiFeetPicture, WikiFeetSqlBase
from slashbot.core.logger import Logger


class ModelNotFoundOnWikiFeetError(Exception):
    """Raised when a model is not found on WikiFeet during scraping."""


class ModelNotFoundInDatabaseError(Exception):
    """Raised when a model is not found in the local database."""


class ModelDataParseError(Exception):
    """Raised when there is an error parsing model data from WikiFeet."""


class DuplicateCommentError(Exception):
    """Raised when attempting to add a duplicate comment to the database."""


class DuplicateImageError(Exception):
    """Raised when attempting to add a duplicate image to the database."""


class DuplicateModelError(Exception):
    """Raised when attempting to add a duplicate model to the database."""


class WikiFeetScraper(Logger):
    """A class for scraping a model's best pictures from Wikifeet."""

    def __init__(self) -> None:
        """Initialise the WikiFeetScraper class."""
        super().__init__(prepend_msg="[WikiFeetScraper]")

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
        self.driver.install_addon("data/uBlock.firefox.xpi", temporary=True)
        self.wait = WebDriverWait(self.driver, timeout=20)

    def __del__(self) -> None:
        """Ensure the browser is closed when the object is destroyed."""
        if hasattr(self, "driver"):
            self.driver.quit()

    @staticmethod
    def capitalise_name(model_name: str) -> str:
        """Capitalise a model's name.

        Parameters
        ----------
        model_name : str
            The name of the model.

        Returns
        -------
        str
            The capitalised name.

        """
        return " ".join(part.capitalize() for part in model_name.split())

    def make_url_model_name(self, model_name: str) -> str:
        """Convert a model's name to the WikiFeet URL format.

        Parameters
        ----------
        model_name : str
            The name of the model.

        Returns
        -------
        str
            The formatted model name for the URL.

        """
        return self.capitalise_name(model_name).replace(" ", "_")

    @staticmethod
    def _parse_model_json_from_response(html: str, extract_pattern: str) -> dict:
        """Extract model data from the WikiFeet HTML.

        Parameters
        ----------
        html : str
            The HTML content of the WikiFeet model page.
        extract_pattern : str
            The pattern to extract json starting from.

        Returns
        -------
        dict
            A dictionary containing the model data.

        """
        start_index = html.find(extract_pattern)
        if start_index == -1:
            msg = "Could not find model data in HTML"
            raise ValueError(msg)

        start_index = start_index + len(extract_pattern) - 1
        end_index = html.find("\n", start_index) - 1
        model_json_string = html[start_index:end_index]

        return json.loads(model_json_string)

    @staticmethod
    def _get_model_data(data: dict, key: str, default: Any) -> Any:
        """Extract data from a model dict and set a default if missing.

        Parameters
        ----------
        data : dict
            The dict containing the model data.
        key : str
            The key of the dict to extract.
        default : Any
            A default value if key is missing a value or is null.

        Returns
        -------
        Any
            The value of key or the default value provided.

        """
        value = data.get(key, default)
        if not value:
            value = default

        return value

    async def _extract_json_from_model_page(self, model_name: str, extract_pattern: str) -> dict:
        model_url = self.make_url_model_name(model_name)

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.get(f"https://wikifeet.com/{model_url}")
                response.raise_for_status()
            except httpx.HTTPError as e:
                exc_msg = f"Unable to get scrape WikiFeet for {model_name}"
                self.log_exception("%s", exc_msg)
                raise ModelNotFoundOnWikiFeetError(exc_msg) from e

        try:
            data = self._parse_model_json_from_response(response.text, extract_pattern)
        except (ValueError, json.JSONDecodeError) as e:
            exc_msg = f"Unable to parse scraped data for {model_name}"
            self.log_exception("%s", exc_msg)
            self.log_debug(f"Response: {response.text}")
            raise ModelNotFoundOnWikiFeetError(exc_msg) from e

        return data

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
        data = await self._extract_json_from_model_page(model_name, "tdata = ")
        if "cname" not in data:
            exc_msg = f"{model_name} not found on WikiFeet"
            raise ModelNotFoundOnWikiFeetError(exc_msg)

        now = datetime.datetime.now(tz=datetime.UTC)

        try:
            model = WikiFeetModel(
                name=data["cname"],
                last_updated=now,
                foot_score=self._get_model_data(data, "score", 0),
                shoe_size=(float(self._get_model_data(data, "ssize", -3) + 3)) / 2,
            )
            self.log_debug(f"Created model instance for {model.name}: {model}")
        except (KeyError, ValueError, IndexError, TypeError) as e:
            exc_msg = f"Error parsing model data for {model_name}"
            self.log_exception("%s %s: %s", e, exc_msg, data)
            raise ModelDataParseError(exc_msg) from e

        return model

    async def get_model_comments(self, model_name: str) -> list[dict]:
        """Get comments about the model.

        Parameters
        ----------
        model_name : str
            The name of the model to get comments for.

        Returns
        -------
        list[dict]
            A list of comments.

        """
        data = await self._extract_json_from_model_page(model_name, "tdata = ")
        if "cname" not in data:
            exc_msg = f"{model_name} not found on WikiFeet"
            raise ModelNotFoundOnWikiFeetError(exc_msg)

        return data.get("comments", {}).get("threads", [])

    def _handle_cookie_banner(self, timeout: int = 2) -> None:
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
        self.log_debug(f"Scraping {self.base_url}/{model_name_url}")
        self.driver.get(f"{self.base_url}/{model_name_url}")

        # thank you to the EU
        self._handle_cookie_banner()

        # Sort images by "best" by clicking the filter buttons
        self._scroll_and_click(By.CSS_SELECTOR, "div.latest")
        self._scroll_and_click(By.XPATH, "//div[contains(text(), 'Best')]")

        # Wait for the sorted pictures to be present in the DOM
        self.wait.until(lambda driver: driver.find_element(By.XPATH, "//div[starts-with(@id, 'pid_')]"))

        # Find all picture elements and extract their IDs
        picture_elements = self.driver.find_elements(By.XPATH, "//div[starts-with(@id, 'pid_')]")
        picture_ids = [elem.get_attribute("id") for elem in picture_elements]
        self.log_debug(f"Pictures found for {self.base_url}/{model_name_url}: {picture_ids}")

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
        self._db_lock = asyncio.Lock()

    async def init_database(self) -> None:
        """Initialize the database and create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(WikiFeetSqlBase.metadata.create_all)

    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[AsyncSession, None]:
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

    async def _add_new_model(self, model: WikiFeetModel) -> WikiFeetModel:
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
        async with self._get_session() as session:
            try:
                session.add(model)
                await session.commit()
                await session.refresh(model)
            except IntegrityError as e:
                await session.rollback()
                exc_msg = f"Model {model.name} already exists in database"
                self.log_error("%s", exc_msg)
                raise DuplicateModelError(exc_msg) from e
            else:
                return model

    async def _add_model_picture(self, picture: WikiFeetPicture) -> None:
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
        async with self._get_session() as session:
            try:
                session.add(picture)
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                exc_msg = f"Picture {picture.picture_id} already exists in database for model id {picture.model_id}"
                self.log_error("%s", exc_msg)
                raise DuplicateImageError(exc_msg) from e

    async def _add_model_comment(self, comment: WikiFeetComment) -> None:
        """Add a WikiFeetPicture instance to the database.

        Parameters
        ----------
        comment : WikiFeetComment
            The comment instance to add.

        """
        async with self._get_session() as session:
            try:
                session.add(comment)
                await session.commit()
            except IntegrityError as e:
                await session.rollback()
                exc_msg = f"Comment already exists in database for model id {comment.model_id}"
                self.log_error("%s", exc_msg)
                raise DuplicateCommentError(exc_msg) from e

    async def _add_model_pictures(self, model_name: str, model_id: int) -> None:
        """Update the pictures for a model.

        Parameters
        ----------
        model_name : str
            The name of the model.
        model_id : int
            The database ID of the model.

        """
        model_name = self.scraper.capitalise_name(model_name)
        ids_best_pictures = self.scraper.get_best_images_for_model(self.scraper.make_url_model_name(model_name))

        for pid in ids_best_pictures:
            try:
                await self._add_model_picture(WikiFeetPicture(model_id=model_id, picture_id=pid))
            except DuplicateImageError:
                continue

    async def _add_model_comments(self, model_name: str, model_id: int) -> None:
        """Update the comments for a model.

        Parameters
        ----------
        model_name : str
            The name of the model.
        model_id : int
            The database ID of the model.

        """
        model_name = self.scraper.capitalise_name(model_name)
        comments = await self.scraper.get_model_comments(model_name)

        for comment in comments:
            try:
                await self._add_model_comment(
                    WikiFeetComment(
                        model_id=model_id,
                        comment=comment["comment"],
                        user=comment["nickname"],
                        user_title=comment.get("title", ""),
                    )
                )
            except DuplicateCommentError:
                continue

    async def get_model(self, model_name: str) -> WikiFeetModel:
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
        model_name = self.scraper.capitalise_name(model_name)

        async with self._get_session() as session:
            query = select(WikiFeetModel).where(WikiFeetModel.name == model_name)
            result = await session.execute(query)
            model = result.scalar_one_or_none()
            if model:
                return model

            # Create the model if missing
            self.log_debug(f"Scraping info and images for {model_name}")
            model_info = await self.scraper.get_model_info(model_name)
            model = await self._add_new_model(model_info)
            await self._add_model_pictures(model_name, model.id)
            await self._add_model_comments(model_name, model.id)

            return model

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
        model_name = self.scraper.capitalise_name(model_name)
        model = await self.get_model(model_name)

        async with self._get_session() as session:
            stmt = (
                select(WikiFeetModel).options(selectinload(WikiFeetModel.pictures)).where(WikiFeetModel.id == model.id)
            )
            result = await session.execute(stmt)
            model_with_pictures = result.scalar_one_or_none()

        return model_with_pictures.pictures if model_with_pictures else []

    async def get_model_comments(self, model_name: str) -> list[WikiFeetComment]:
        """Retrieve a model's comments.

        Parameters
        ----------
        model_name : str
            The name of the model.

        Returns
        -------
        list[WikiFeetComment]
            A list containing wikiFeetcomment objects.

        """
        model_name = self.scraper.capitalise_name(model_name)
        model = await self.get_model(model_name)

        async with self._get_session() as session:
            stmt = (
                select(WikiFeetModel).options(selectinload(WikiFeetModel.comments)).where(WikiFeetModel.id == model.id)
            )
            result = await session.execute(stmt)
            model_with_comments = result.scalar_one_or_none()

        return model_with_comments.comments if model_with_comments else []
