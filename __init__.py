"""
Add extra functionality to the Plex integration.

For more details about this component, please refer to the documentation at
https://github.com/constructorfleet/HomeAssistant-Component-BetterPlex
"""
import logging
from random import randint
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.media_player.const import (
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_CONTENT_ID,
    SERVICE_PLAY_MEDIA
)
from homeassistant.components.plex import (
    PLEX_DOMAIN,
    SERVERS
)
from homeassistant.components.plex.media_player import (
    PlexMediaPlayer
)
from homeassistant.const import (
    ATTR_ENTITY_ID
)
from homeassistant.helpers.typing import (
    HomeAssistantType,
    ConfigType
)
from plexapi.library import Library
from plexapi.video import Video

from .const import (
    ATTR_GENRES,
    ATTR_MEDIA_TITLE,
    ATTR_PICK_RANDOM,
    ATTR_SERVER_NAME,
    CONF_DEFAULT_SERVER_NAME,
    SERVICE_SEARCH_AND_PLAY,
    VALID_MEDIA_TYPES
)

_LOGGER = logging.getLogger(__name__)
MEDIA_PLAYER_DOMAIN = 'media_player'

CONFIG_SCHEMA = vol.Schema(
    {
        'better_plex': vol.Schema({
            vol.Optional(CONF_DEFAULT_SERVER_NAME): cv.string,
        }),
    },
    extra=vol.ALLOW_EXTRA
)


def _get_media_player_by_entity_id(
        hass: HomeAssistantType,
        entity_id: str
) -> Optional[PlexMediaPlayer]:
    entity = hass.data[MEDIA_PLAYER_DOMAIN].get_entity(entity_id)
    if not entity:
        _LOGGER.error(
            "Unable to locate entity with id %s",
            entity_id
        )
        return None

    if not isinstance(entity, PlexMediaPlayer):
        _LOGGER.error(
            "Entity with id %s is not a PlexMediaPlayer",
            entity
        )
        return None

    return entity


def _search(
        hass: HomeAssistantType,
        media_content_type: str,
        server_name: str = None,
        media_title: str = None,
        pick_random: bool = False,
        # season_number: int = None,
        # episode_number: int = None,
        genres=None
) -> Optional[Video]:
    server_name = server_name
    plex_server_library = _get_plex_server_library_by_name(hass, server_name)
    if not plex_server_library:
        return
    media_items = _get_library_items_of_type(
        hass,
        plex_server_library,
        media_content_type
    )
    if not media_items:
        return

    if genres:
        media_items = _filter_items_by_genre(
            media_items,
            genres
        )
        if not media_items:
            return

    if pick_random:
        if media_items:
            return media_items[randint(0, len(media_items) - 1)]  # TODO: Play it
    elif media_title:
        media_items = _filter_items_by_title(
            media_items,
            media_title
        )
        if media_items:
            return media_items[0]['media_item']

    _LOGGER.error(
        "Unable to find any matching media items."
    )
    return None


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
        for server_id, server
        in hass.data[PLEX_DOMAIN][SERVERS].items()
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
        hass: HomeAssistantType,
        plex_server_library: Library,
        media_content_type: str
):
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
        media_items,
        genres
):
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
        media_items,
        media_title
):
    from fuzzywuzzy import fuzz

    matching_items = [
        {
            "media_item": item,
            "match": fuzz.WRatio(
                media_title.lower(),  # re.sub(NON_ALPHA_NUMERIC_REGEX_PATTERN, "", media_title).lower(),
                item.title.lower(),  # re.sub(NON_ALPHA_NUMERIC_REGEX_PATTERN, "", item.title).lower(),
                full_process=True
            )
        }
        for item
        in media_items
    ]

    if not matching_items:
        _LOGGER.error(
            "Unable to find any items with title close to %s",
            media_title
        )
        return None

    return sorted(matching_items, key=lambda item: item['match'], reverse=True)


async def async_setup(
        hass: HomeAssistantType,
        config: ConfigType
):
    conf = config.get('better_plex')

    def _play_search_result(
            entity,
            media_content_type,
            server_name,
            media_title=None,
            season_number=None,
            episode_number=None,
            genres=None,
            pick_random=False
    ):
        search_result = _search(hass,
                                media_content_type,
                                server_name or conf.get(CONF_DEFAULT_SERVER_NAME, None),
                                media_title,
                                pick_random=pick_random,
                                # season_number=season_number,
                                # episode_number=episode_number,
                                genres=None)

        if not search_result:
            _LOGGER.error("No media items match the search criteria")
            return

        if not search_result.ratingKey:
            _LOGGER.error(
                "Unable to determine the unique identifier for media item %s",
                search_result.title
            )
            return

        hass.services.call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                ATTR_ENTITY_ID: entity.entity_id,
                ATTR_MEDIA_CONTENT_TYPE: media_content_type,
                ATTR_MEDIA_CONTENT_ID: search_result.ratingKey
            }
        )

    async def handle_play_search_result(
            service
    ):
        entity_id = service.data.get(ATTR_ENTITY_ID)
        media_content_type = service.data.get(ATTR_MEDIA_CONTENT_TYPE)
        server_name = service.data.get(ATTR_SERVER_NAME, conf.get(CONF_DEFAULT_SERVER_NAME, None))
        media_title = service.data.get(ATTR_MEDIA_TITLE, None)
        pick_random = service.data.get(ATTR_PICK_RANDOM, False)
        # season_number: int = None,
        # episode_number: int = None,
        genres = service.data.get(ATTR_GENRES, None)

        entity = _get_media_player_by_entity_id(
            hass,
            entity_id
        )
        if not entity:
            return

        await hass.async_add_job(
            _play_search_result(
                entity,
                media_content_type,
                server_name, media_title,
                genres=genres,
                pick_random=pick_random))

    search_and_play_schema = vol.Schema(
        {
            vol.Required(ATTR_ENTITY_ID): cv.string,
            vol.Required(ATTR_SERVER_NAME, default=conf[CONF_DEFAULT_SERVER_NAME]): cv.string,
            vol.Exclusive(ATTR_MEDIA_TITLE, 'specific_or_random'): cv.string,
            vol.Exclusive(ATTR_PICK_RANDOM, 'specific_or_random'): cv.boolean,
            # vol.Optional(ATTR_SEASON_NUMBER): cv.positive_int,
            # vol.Optional(ATTR_EPISODE_NUMBER): cv.positive_int,
            vol.Required(ATTR_MEDIA_CONTENT_TYPE): vol.All(cv.string, vol.In(VALID_MEDIA_TYPES)),
            vol.Optional(ATTR_GENRES): vol.All(
                cv.ensure_list,
                [cv.string]
            )
        }
    )

    hass.services.async_register(
        'better_plex',
        SERVICE_SEARCH_AND_PLAY,
        handle_play_search_result,
        search_and_play_schema
    )

    return True
