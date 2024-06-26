"""Middle-layer which defines the API used by the bot.

The point of this module is to create aliases to the API client and various
types that are used in the command library. The point of this is to try and make
the command library agnostic to the client used, assuming they are all forks
of Discord.py.

The current API client is Disnake.
"""

import disnake

# Alias for API client, if we want to use it
discord = disnake

# Aliases for typing
ApplicationCommandInteraction = disnake.ApplicationCommandInteraction
Interaction = disnake.Interaction
InteractionReference = disnake.InteractionReference
User = disnake.User
Member = disnake.Member
TextChannel = disnake.TextChannel
DMChannel = disnake.DMChannel
Message = disnake.Message
