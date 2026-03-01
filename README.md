# Slashbot

Slashbot is a Discord bot using Disnake. It is designed to work in only a few servers, so there are some hardcoded
values here and there.

## Deployment

Slashbot is designed to be run using Docker. Slashbot requires multiple API keys which should be put in an .env file.
Once you have configured your API keys, launch Slashbot using:

```bash
docker compose up
```

## Development

Slashbot can be run in a debug mode with additional logging and automatic cog reloading when a change is detected.
This is enabled with the `--debug` flag, e.g.:

```bash
uv run slashbot --debug
```

To launch Slashbot in a container in debug mode, use:

```bash
DEBUG=true docker compose up
```
