# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

WORKDIR /bot
SHELL ["/bin/bash", "-c"]

COPY requirements.txt requirements.txt
RUN python3 -m venv /bot/venv
RUN source /bot/venv/bin/activate
RUN python -m pip install -r requirements.txt
COPY . .

CMD ["python", "run.py"]
