# Slashbot

Slashbot is Discord bot written using the Disnake package, based on my previous
bot Badbot/Adminbot. It is designed to only work on a few servers which I
am in, here there are some hardcoded IDs and specifc features.

## Deployment

slashbot can be deployed using docker and docker-compose,

```bash
docker compose up
```

For development,

```bash
docker compose -f docker-compose.develop.yml up
```

## Requirements

Python 3.10 or above is required. I use Python 3.11 because it has nicer
error messages and is faster. Python requirements are in `requirements.txt`
or can be installed with Poetry.

The following environment variables are required,

```output
SLASHBOT_CONFIG               # Path to config file
SLASHBOT_TOKEN                # Token for the bot
SLASHBOT_DEVELOPMENT_TOKEN    # Optional token for development
GOOGLE_API_KEY                # API key for Google, used for Geolocating
WOLFRAM_API_KEY               # Wolfram API key
OWM_API_KEY                   # OpenWeatherMap API key
OPENAI_API_KEY                # OpenAI ChatGPT API key for chat
MONSTER_API_KEY               # Monster AI key for AI image generation
```
