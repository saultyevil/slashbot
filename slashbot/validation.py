from pydantic import BaseModel, Field, field_validator


class ScheduledPost(BaseModel):
    """Pydantic model for scheduled posts."""

    title: str
    files: str | list[str] | None = None
    channels: int | list[int]
    users: list[int] | None = Field(default_factory=list)
    day: int
    hour: int
    minute: int
    markov_seed_word: str | None = None
    message: str | None = None
    time_until_post: float | int | None = None

    @field_validator("day")
    @classmethod
    def _validate_day(cls, value: int) -> int:
        if not (0 <= value <= 6):  # noqa: PLR2004
            msg = "day must be between 0 and 6"
            raise ValueError(msg)
        return value

    @field_validator("hour")
    @classmethod
    def _validate_hour(cls, value: int) -> int:
        if not (0 <= value <= 23):  # noqa: PLR2004
            msg = "hour must be between 0 and 23"
            raise ValueError(msg)
        return value

    @field_validator("minute")
    @classmethod
    def _validate_minute(cls, value: int) -> int:
        if not (0 <= value <= 59):  # noqa: PLR2004
            msg = "minute must be between 0 and 59"
            raise ValueError(msg)
        return value

    @field_validator("channels")
    @classmethod
    def _validate_channels(cls, value: int | list[int]) -> int | list[int]:
        if isinstance(value, list):
            if not all(isinstance(item, int) for item in value):
                msg = "all items in channels must be integers"
                raise ValueError(msg)
        elif not isinstance(value, int):
            msg = "channels must be an integer or a list of integers"
            raise TypeError(msg)
        return value

    @field_validator("files", mode="before")
    @classmethod
    def _validate_files(cls, value: str | list[str] | None) -> str | list[str] | None:
        if value is None:
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        msg = "files must be a string or a list of strings"
        raise ValueError(msg)
