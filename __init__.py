"""
Add extra functionality to the Plex integration.

For more details about this component, please refer to the documentation at
https://github.com/constructorfleet/HomeAssistant-Component-BetterPlex
"""
import functools
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
from homeassistant.core import callback
from homeassistant.helpers.typing import (
    HomeAssistantType,
    ConfigType
)
from plexapi.library import Library
from plexapi.video import Video
from fuzzywuzzy import fuzz

from .const import (
    ATTR_GENRES,
    ATTR_MEDIA_TITLE,
    ATTR_SHOW_NAME,
    ATTR_PICK_RANDOM,
    ATTR_SERVER_NAME,
    CONF_DEFAULT_SERVER_NAME,
    SERVICE_SEARCH_AND_PLAY,
    VALID_MEDIA_TYPES, ATTR_SEASON_NUMBER, ATTR_EPISODE_NUMBER
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


async def async_setup(
        hass: HomeAssistantType,
        config: ConfigType
):
    conf = config.get('better_plex')

    def _get_media_player_by_entity_id(
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

    async def _search(
            media_content_type: str,
            server_name: str = None,
            media_title: str = None,
            show_name: str = None,
            pick_random: bool = False,
            season_number: int = None,
            episode_number: int = None
    ) -> Optional[Video]:
        _LOGGER.info('Performing search')
        server_name = server_name
        plex_server_library = _get_plex_server_library_by_name(server_name)
        if not plex_server_library:
            return

        _LOGGER.info('Getting library items')
        media_items = await _search_library(
            plex_server_library,
            title=media_title,
            grandparentTitle=show_name
        )
        # media_items = await _get_library_items_of_type(
        #     plex_server_library,
        #     media_content_type
        # )
        if not media_items:
            _LOGGER.info('No items found')
            return

        # if genres:
        #     media_items = _filter_items_by_genre(
        #         media_items,
        #         genres
        #     )
        #     if not media_items:
        #         _LOGGER.info('No items found')
        #         return
        #
        # if media_title:
        #     media_items = _filter_items_by_title(
        #         media_items,
        #         media_title
        #     )

        _LOGGER.info('ITEMS %s', str(media_items))

        if media_items:
            if pick_random:
                return media_items[randint(0, len(media_items) - 1)]
            if media_items:
                return media_items[0]

        _LOGGER.error(
            "Unable to find any matching media items."
        )
        return None

    def _get_plex_server_library_by_name(
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

    async def _search_library(
            plex_server_library: Library,
            libtype: str,
            title: str = None,
            **kwargs
    ):
        return await hass.loop.run_in_executor(
            None,
            functools.partial(
                plex_server_library.search,
                title=title,
                libtype=libtype,
                **kwargs
            )
        )

    async def _get_library_items_of_type(
            plex_server_library: Library,
            media_content_type: str
    ):
        results = await hass.async_add_executor_job(plex_server_library.search, None, media_content_type.lower())
        matching_items = [
            item for
            item
            in results
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
            if hasattr(item, 'genres') and len([
                genre
                for genre
                in genres
                if [fuzz.WRatio(
                    item.genre.lower(),  # re.sub(NON_ALPHA_NUMERIC_REGEX_PATTERN, "", media_title).lower(),
                    genre.title.lower(),  # re.sub(NON_ALPHA_NUMERIC_REGEX_PATTERN, "", item.title).lower(),
                    full_process=True
                ) > 95]]) > 0
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

        _LOGGER.info('Performing fuzzy match')
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

        _LOGGER.info('Sorting')
        return [item['media_item'] for item in sorted(matching_items, key=lambda item: item['match'], reverse=True)]

    async def _perform_search(service):
        entity_id = service.data.get(ATTR_ENTITY_ID)
        media_content_type = service.data.get(ATTR_MEDIA_CONTENT_TYPE)
        server_name = service.data.get(ATTR_SERVER_NAME, conf.get(CONF_DEFAULT_SERVER_NAME, None))
        media_title = service.data.get(ATTR_MEDIA_TITLE, None)
        pick_random = service.data.get(ATTR_PICK_RANDOM, False)
        season = service.data.get(ATTR_SEASON_NUMBER, 1)
        episode = service.data.get(ATTR_EPISODE_NUMBER, 1)
        genres = service.data.get(ATTR_GENRES, None)

        entity = _get_media_player_by_entity_id(
            entity_id
        )
        if not entity:
            return

        search_result = await _search(media_content_type,
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

        _LOGGER.info('Invoking service')
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_PLAY_MEDIA,
            {
                ATTR_ENTITY_ID: entity.entity_id,
                ATTR_MEDIA_CONTENT_TYPE: media_content_type,
                ATTR_MEDIA_CONTENT_ID: search_result.ratingKey
            }
        )

    @callback
    def handle_play_search_result(
            service
    ):
        hass.loop.create_task(_perform_search(service))
        return True

    search_and_play_schema = vol.Schema(
        {
            vol.Required(ATTR_ENTITY_ID): cv.string,
            vol.Required(ATTR_SERVER_NAME, default=conf[CONF_DEFAULT_SERVER_NAME]): cv.string,
            vol.Optional(ATTR_MEDIA_TITLE): cv.string,
            vol.Optional(ATTR_SHOW_NAME): cv.string,
            vol.Optional(ATTR_PICK_RANDOM): cv.boolean,
            vol.Optional(ATTR_SEASON_NUMBER): cv.positive_int,
            vol.Optional(ATTR_EPISODE_NUMBER): cv.positive_int,
            vol.Required(ATTR_MEDIA_CONTENT_TYPE): vol.All(cv.string, vol.In(VALID_MEDIA_TYPES))
        }
    )

    hass.services.async_register(
        'better_plex',
        SERVICE_SEARCH_AND_PLAY,
        handle_play_search_result,
        schema=search_and_play_schema
    )

    return True
