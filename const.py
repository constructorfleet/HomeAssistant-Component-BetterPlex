import re
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_EPISODE,
    MEDIA_TYPE_MOVIE,
    MEDIA_TYPE_MUSIC,
    MEDIA_TYPE_TVSHOW
)

ATTR_GENRES = 'genres'
ATTR_LIBRARY = 'library'
ATTR_MEDIA_CONTENT_TYPE = 'media_content_type'
ATTR_MEDIA_TITLE = 'media_title'
ATTR_SEASON_NUMBER = 'season'
ATTR_SHOW_NAME = 'show_name'
ATTR_EPISODE_NUMBER = 'episode'
ATTR_PICK_RANDOM = 'pick_random'
ATTR_SERVER_NAME = 'server_name'

CONF_DEFAULT_SERVER_NAME = 'default_server_name'

SERVICE_SEARCH_AND_PLAY = 'search_and_play'
MEDIA_TYPE_SHOW = "show"

VALID_MEDIA_TYPES = [
    MEDIA_TYPE_EPISODE,
    MEDIA_TYPE_MOVIE,
    # MEDIA_TYPE_MUSIC,
    # MEDIA_TYPE_SHOW
]

NON_ALPHA_NUMERIC_REGEX_PATTERN = re.compile("[^0-9a-zA-Z ]+")
