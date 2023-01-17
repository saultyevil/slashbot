# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

WORKDIR /bot
SHELL ["/bin/bash", "-c"]

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "run.py"]

