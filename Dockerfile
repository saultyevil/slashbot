# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

WORKDIR /bot
SHELL ["/bin/bash", "-c"]

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt
RUN apt update && apt install -y git openssh-client

RUN git config --global --add safe.directory /bot

RUN useradd -m user
RUN mkdir -p /home/user/.ssh
RUN chown -R user:user /home/user/.ssh
USER user

# COPY . .
CMD ["python", "run.py"]
