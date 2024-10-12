# Slashbot

Slashbot is a Discord bot using Disnake. It is designed to work in only a few
servers, so there are some hardcoded values here and there.

## Deployment

Slashbot is designed to be run using Docker. Slashbot requires multiple API
keys which should be put in the provided .env file.

Once you have configured your API keys, launch Slashbot using

```bash
docker compose up
```

For development versions of the bot, use

```bash
docker compose -f docker-compose.develop.yml up
```

## Development requirements

I'm not sure what the minimum version of Python this works on. I have developed
the bot mostly using Python 3.10 or 3.11. The package requirements can be
installed using either poetry of the `requirements.txt` file.
