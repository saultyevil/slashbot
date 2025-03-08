# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

# Install poetry via pip
RUN pip install poetry

# Copy the poetry files to cache them in docker layer
WORKDIR /bot
COPY poetry.lock pyproject.toml README.md ./
RUN poetry install --no-interaction --no-ansi --no-root

# Run the bot
CMD ["./entrypoint.sh"]
