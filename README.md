# Slashbot

Slashbot is Discord bot written using the Disnake package, based on my previous
bot Badbot/Adminbot. It is designed to only work on a few servers which I
am in, here there are some hardcoded IDs and specifc features.

## Deployment

slashbot can be deployed using docker and docker-compose,

```bash
$ docker-compose up -d --build
```

You will need the environment variables listed in the next section in a file
named `docker-env.env`.

## Requirements

Python 3.7 or above is required. I use Python 3.11 because it has nicer
error messages and is faster. Requirements for development are in
`requirements-dev.txt` with requirements for running it in `requirements.txt`.

The following environment variables are required,

```
export BOT_TOKEN="XXXXXXXXXXXXXXXXXXXX"       # the discord bot token
export OWM_KEY="XXXXXXXXXXXXXXXXXXXX"         # an open weather map api key
export WOLFRAM_ID="XXXXXXXXXXXXXXXXXXXX"      # a wolfram alpha api key
```
