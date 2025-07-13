import datetime
import json
from collections.abc import AsyncGenerator

import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from slashbot.core.database.models import WikiFeetModel, WikiFeetPicture, WikiFeetSqlBase
from slashbot.core.logger import Logger


class WikiFeetScraper(Logger):
    """A class for scraping a model's best pictures from Wikifeet."""

    def __init__(self, database: "WikiFeetDatabase") -> None:
        """Initialise the WikiFeetScraper class with a WikiFeetDatabase.

        Parameters
        ----------
        database : WikiFeetDatabase
            A WikiFeetDatabase class to update.

        """
        timeout = 10
        self.database = database

        options = webdriver.ChromeOptions()
        # options.add_argument("--headless=new")

        self.base_url = "https://wikifeet.com"
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, timeout)

    @staticmethod
    def _make_url_model_name(name: str) -> str:
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
        list[str]
            A list of picture IDs found in the gallery.

        """
        json_symbol = "tdata = "
        start_index = html.find(json_symbol)
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
        model_url = self._make_url_model_name(model_name)
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://wikifeet.com/{model_url}", timeout=2)

        if response.status_code != httpx.codes.OK:
            exc_msg = f"Unable to get webpage for {model_name}"
            self.database.log_error("%s", exc_msg)
            raise ValueError(exc_msg)

        data = self._get_model_data(response.text)

        now = datetime.datetime.now(tz=datetime.UTC)
        birthday = datetime.datetime.fromisoformat(data["bdate"].replace("Z", "+00:00"))
        age = now.year - birthday.year - ((now.month, now.day) < (birthday.month, birthday.day))
        height_feet = float(data["height_us"][0])
        height_inches = float(data["height_us"][1:])
        height_cm = height_feet * 30.48 + height_inches * 2.54

        return WikiFeetModel(
            name=data["cname"],
            last_updated=now,
            foot_score=data["score"],
            shoe_size=data["ssize"],
            height_cm=height_cm,
            age=age,
            nationality=data["edata"]["nationality"],
        )

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

        # Sort images by "best"
        latest_div = self.wait.until(expected_conditions.element_to_be_clickable((By.CSS_SELECTOR, "div.latest")))
        latest_div.click()
        best_option = self.wait.until(
            expected_conditions.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Best')]"))
        )
        best_option.click()
        self.wait.until(expected_conditions.presence_of_element_located((By.XPATH, "//div[starts-with(@id, 'pid_')]")))

        # Return list of picture ids
        picture_ids = [
            div.get_attribute("id") for div in self.driver.find_elements(By.XPATH, "//div[starts-with(@id, 'pid_')]")
        ]

        # Remove any Nones and extract just the id to we return `id`` and not `pid_id`
        return [picture_id.split("_")[-1] for picture_id in picture_ids if picture_id]

    async def update_model_pictures(self, model_name: str) -> None:
        """Update the pictures for a model.

        Parameters
        ----------
        model_name : str
            The name of the model.

        """
        ids_best_pictures = self.get_best_images_for_model(self._make_url_model_name(model_name))

        if "_" in model_name:
            model_name = model_name.replace("_", " ")
        await self.database.init_database()
        model = await self.database.get_model(model_name)
        if not model:
            raise NotImplementedError
        for pid in ids_best_pictures:
            try:
                await self.database.add_picture(WikiFeetPicture(model_id=model.id, picture_id=pid))
            except ValueError:
                continue


class WikiFeetDatabase(Logger):
    """A class to interact with the WikiFeet database."""

    def __init__(self, database_url: str) -> None:
        """Initialize the WikiFeetDatabase with a database URL.

        Parameters
        ----------
        database_url : str
            The database connection URL.

        """
        super().__init__(prepend_msg="[WikiFeetDatabase]")
        self.engine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.scraper = WikiFeetScraper(self)

    async def init_database(self) -> None:
        """Initialize the database and create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(WikiFeetSqlBase.metadata.create_all)

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Asynchronous context manager for database session.

        Returns
        -------
        AsyncGenerator[AsyncSession, None]
            An async generator yielding an AsyncSession.

        """
        async with self.session_factory() as session:
            yield session

    async def add_model(self, model: WikiFeetModel) -> None:
        """Add a WikiFeetModel instance to the database.

        Parameters
        ----------
        model : WikiFeetModel
            The model instance to add.

        """
        async for session in self.get_session():
            model_query = select(WikiFeetModel).where(WikiFeetModel.name == model.name)
            result = await session.execute(model_query)

            if result.scalar_one_or_none():
                exc_msg = f"Trying to add {model.name} to database when the entry already exists"
                self.log_error("%s", exc_msg)
                raise ValueError(exc_msg)

            session.add(model)
            await session.commit()

    async def add_picture(self, picture: WikiFeetPicture) -> None:
        """Add a WikiFeetPicture instance to the database.

        Parameters
        ----------
        picture : WikiFeetPicture
            The picture instance to add.

        """
        async for session in self.get_session():
            picture_query = select(WikiFeetPicture).where(WikiFeetPicture.picture_id == picture.picture_id)
            result = await session.execute(picture_query)

            if result.scalar_one_or_none():
                exc_msg = "Trying to add a picture which already exists"
                self.log_error("%s", exc_msg)
                raise ValueError(exc_msg)

            session.add(picture)
            await session.commit()

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
        async for session in self.get_session():
            query = select(WikiFeetModel).where(WikiFeetModel.name == model_name)
            model = await session.execute(query)

        model = model.scalar_one_or_none()

        if model:
            return model

        model_info = await self.scraper.get_model_info(model_name)
        await self.add_model(model_info)
        model = await self.get_model(model_name)
        await self.scraper.update_model_pictures(model_name)

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
        async for session in self.get_session():
            stmt = (
                select(WikiFeetModel)
                .options(selectinload(WikiFeetModel.pictures))
                .where(WikiFeetModel.name == model_name)
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

        if model is None:
            await self.get_model(model_name)
            pictures = await self.get_model_pictures(model_name)
            return pictures

        return model.pictures
