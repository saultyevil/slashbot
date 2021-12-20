#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

# Constants defined for controlling cooldowns

cooldown_rate = 2
cooldown_standard = 20
cooldown_one_hour = 3600
cooldown_ten_mins = 600
hours_in_week = 168

# Constants for general discord things

symbol = "%"
max_chars = 1994

# Constants to define users, roles and channels. Note that users are supposed
# to be set as environment variables for privacy reasons.

id_bot = 815234903251091456
id_user_adam = 261097001301704704
id_user_zadeth = 737239706214858783
id_user_lime = 121310675132743680
id_user_saultyevil = 151378138612367360
id_user_hypnotized = 176726054256377867
id_server_adult_children = 237647756049514498
id_server_freedom = 815237689775357992
id_server_bumpaper = 710120382144839691
id_channel_idiots = 237647756049514498
id_channel_spam = 627234669791805450

slash_servers = [
    id_server_adult_children,
    id_server_freedom,
    id_server_bumpaper
]


# Constants for the chat bot

badword = os.environ["BAD_WORD"].lower()
badword_plural = badword + "s"

# API keys and specific settings

google_api_key = os.getenv("YT_VIDEO_KEY")
wolfram_api_key = os.getenv("WOLFRAM_ID")
openweathermap_api_key = os.getenv("OWM_KEY")
newsapi_key = os.getenv("NEWS_API")
