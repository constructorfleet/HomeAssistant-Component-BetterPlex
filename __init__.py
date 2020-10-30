"""
Add extra functionality to the Plex integration.

For more details about this component, please refer to the documentation at
https://github.com/constructorfleet/HomeAssistant-Component-BetterPlex
"""
import logging
from random import randint
from typing import Iterable, Optional
import voluptuous as vol

from homeassistant.const import (
    ATTR_ENTITY_ID
)
import homeassistant.helpers.config_validation as cv
from homeassistant.components.media_player.const import (
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_CONTENT_ID,
    MEDIA_TYPE_EPISODE,
    MEDIA_TYPE_GENRE,
    MEDIA_TYPE_MOVIE,
    MEDIA_TYPE_MUSIC,
    MEDIA_TYPE_TVSHOW,
    SERVICE_PLAY_MEDIA
)
from homeassistant.components.plex import (
    PLEX_DOMAIN,
    SERVERS,
    PlexServer
)
from homeassistant.components.plex.media_player import (
    PlexMediaPlayer
)
from homeassistant.helpers.typing import (
    HomeAssistantType,
    ConfigType
)

from .const import (
    ATTR_EPISODE_NUMBER,
    ATTR_GENRES,
    ATTR_MEDIA_TITLE,
    ATTR_PICK_RANDOM,
    ATTR_SEASON_NUMBER,
    ATTR_SERVER_NAME,
    CONF_DEFAULT_SERVER_NAME,
    SERVICE_SEARCH_AND_PLAY,
    VALID_MEDIA_TYPES
)

from plexapi.library import Library
from plexapi.base import PlexObject
from plexapi.video import Video, Movie, Show, Season, Episode

from fuzzywuzzy import fuzz

_LOGGER = logging.getLogger(__name__)
MEDIAPLAYER_DOMAIN = 'media_player'
DOMAIN: 'better_plex'

SEARCH_AND_PLAY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): vol.All(
            cv.string,
            cv.entity_id
        ),
        vol.Optional(ATTR_SERVER_NAME): cv.string,
        vol.Exclusive(ATTR_MEDIA_TITLE, 'specific_or_random'): cv.string,
        vol.Exclusive(ATTR_PICK_RANDOM, 'specific_or_random'): cv.boolean,
        vol.Optional(ATTR_SEASON_NUMBER): cv.positive_int,
        vol.Optional(ATTR_EPISODE_NUMBER): cv.positive_int,
        vol.Required(ATTR_MEDIA_CONTENT_TYPE): vol.All(
            cv.ensure_list,
            [vol.All(cv.string, VALID_MEDIA_TYPES)]
        ),
        vol.Optional(ATTR_GENRES): vol.All(
            cv.ensure_list,
            [cv.string]
        )
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        'better_plex': vol.Schema({
            vol.Optional(CONF_DEFAULT_SERVER_NAME): cv.string,
        }),
    },
    extra=vol.ALLOW_EXTRA
)


def _get_mediaplayer_by_entity_id(
        hass: HomeAssistantType,
        entity_id: str
) -> Optional[PlexMediaPlayer]:
    entity = hass.data[MEDIAPLAYER_DOMAIN].get_entity(entity_id)
    if not entity:
        _LOGGER.error(
            "Unable to locate entity with id %s",
            entity_id
        )
        return None

    if not isinstance(entity, PlexMediaPlayer):
        _LOGGER.error(
            "Entity with id %s is not a PlexMediaPlayer",
            entity_id
        )
        return None

    return entity


def _search(
        media_content_type: str,
        server_name: str = None,
        media_title: str = None,
        pick_random: bool = False,
        season_number: int = None,
        episode_number: int = None,
        genres: Optional[Iterable[str]] = None
) -> Optional[Video]:
    import plexapi.server as plex_api_server

    server_name = server_name if server_name is not None else conf.get(CONF_DEFAULT_SERVER_NAME, None)
    plex_server_library = _get_plex_server_library_by_name(hass, server_name)
    if not plex_server_library:
        return

    media_items = _get_library_items_of_type(
        plex_server_library,
        media_content_type
    )
    if not media_items:
        return

    if media_genre:
        media_items = _filter_items_by_genre(
            media_items,
            genres
        )
        if not media_items:
            return

    if pick_random:
        if media_items:
            return media_items.__getitem__(randint(0, len(media_items)))  # TODO: Play it
    elif media_title:
        media_items = _filter_items_by_title(
            media_items,
            media_title
        )
        if media_items:
            return media_items[0]

    _LOGGER.error(
        "Unable to find any matching media items."
    )
    return


def _get_plex_server_library_by_name(
        hass: HomeAssistantType,
        server_name: str = None
) -> Optional[Library]:
    if server_name is None:
        _LOGGER.error(
            "Missing required argument 'server_name'."
        )
        return None

    matching_plex_servers = [
        server
        for server
        in hass.data[PLEX_DOMAIN][SERVERS]
        if server.friendly_name.lower() == server_name.lower()
    ]
    if not matching_plex_servers:
        _LOGGER.error(
            "Requested Plex server '%s' not found in %s",
            server_name.lower(),
            [
                server.friendly_name.lower()
                for server
                in hass.data[PLEX_DOMAIN][SERVERS]
            ],
        )
        return None

    return matching_plex_servers[0].library


def _get_library_items_of_type(
        plex_server_library: Library,
        media_content_type: str
) -> Optional[Iterable[Video]]:
    matching_items = [
        item for
        item
        in plex_server_library.search(libtype=media_content_type.lower())
        if item.TYPE.lower() == media_content_type.lower()
    ]

    if not matching_items:
        _LOGGER.error(
            "Requested content type '%s' not found in %s",
            media_content_type.lower(),
            [
                library_section.lower()
                for library_section
                in plex_server_library.library.sections()
            ]
        )
        return None

    return matching_items


def _filter_items_by_genre(
        media_items: Iterable[Video],
        genres: Iterable[str]
) -> Optional[Iterable[Video]]:
    if not genres:
        _LOGGER.error(
            "No genres specified to filter by"
        )
        return media_items

    matching_items = [
        item
        for item
        in media_items
        if hasattr(item, 'genres') and list(set(genres) & set(item.genres))
    ]

    if not matching_items:
        _LOGGER.error(
            "No items match the specified genres %s",
            genres
        )
        return None

    return matching_items


def _filter_items_by_title(
        media_items: Iterable[Video],
        media_title: str
) -> Optional[Iterable[Video]]:
    matching_items = [
        {
            "media_item": item,
            "match": fuzz.token_set_ratio(item.title, media_title)
        }
        for item
        in media_items
        if fuzz.token_set_ratio(item.title, media_title) > 85
    ]

    if not matching_items:
        _LOGGER.error(
            "Unable to find any items with title close to %s",
            media_title
        )
        return None

    return sorted(matching_items, key=lambda item: item.match)


async def async_setup(
        hass: HomeAssistantType,
        config: ConfigType
):
    conf = config.get(DOMAIN)

    async def play_search_result(
            entity_id: str,
            media_content_type: str,
            server_name: str = None,
            media_title: str = None,
            pick_random: bool = False,
            season_number: int = None,
            episode_number: int = None,
            genres: Optional[Iterable[str]] = None
    ):
        entity = _get_mediaplayer_by_entity_id(
            hass,
            entity_id
        )
        if not entity:
            return

        search_result = _search(
            media_content_type,
            server_name or conf.get(CONF_DEFAULT_SERVER_NAME, None),
            media_title,
            pick_random=pick_random,
            season_number=season_number,
            episode_number=episode_number,
            genres=genres
        )

        if not search_result:
            _LOGGER.error(
                "No media items match the search criteria"
            )
            return
        if not search_result.ratingKey:
            _LOGGER.error(
                "Unable to determine the unique identifier for media item %s",
                search_result.title
            )
            return

        await hass.services.async_call(
            MEDIAPLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_MEDIA_CONTENT_TYPE: media_content_type,
                ATTR_MEDIA_CONTENT_ID: search_result.ratingKey
            }
        )

    await hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH_AND_PLAY,
        play_search_result,
        SEARCH_AND_PLAY_SCHEMA
    )

    return True
