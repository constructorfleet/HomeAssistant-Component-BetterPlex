"""
Add extra functionality to the Plex integration.

For more details about this component, please refer to the documentation at
https://github.com/constructorfleet/HomeAssistant-Component-BetterPlex
"""
import functools
import itertools
import logging
from random import randint
from typing import Optional

import homeassistant.helpers.config_validation as cv
import plexapi
import voluptuous as vol
from homeassistant.components.media_player.const import (
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_CONTENT_ID,
    SERVICE_PLAY_MEDIA, MEDIA_TYPE_EPISODE, MEDIA_TYPE_MOVIE
)
from homeassistant.components.plex import (
    PLEX_DOMAIN,
    SERVERS
)
from homeassistant.components.plex.media_player import (
    PlexMediaPlayer
)
from homeassistant.components.plex.server import PlexServer
from homeassistant.const import (
    ATTR_ENTITY_ID
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import async_get_registry as get_device_registry
from homeassistant.helpers.entity_registry import async_get_registry as get_entity_registry
from homeassistant.helpers.typing import (
    HomeAssistantType,
    ConfigType
)
from plexapi.server import PlexServer as PlexServerAPI
from plexapi.video import Video

from .const import (
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
            plex_server_library: plexapi.server.PlexServer,
            media_content_type: str,
            media_title: str = None,
            show_name: str = None,
            pick_random: bool = False,
            season_number: int = None,
            episode_number: int = None
    ) -> Optional[Video]:
        _LOGGER.info('Performing search')

        kwargs = {
            'libtype': media_content_type
        }

        if media_content_type == MEDIA_TYPE_EPISODE:
            if show_name is not None:
                kwargs['show.title'] = show_name
            if media_title is not None:
                kwargs['episode.title'] = media_title
            if season_number is not None:
                kwargs['season.index'] = season_number
            if episode_number is not None:
                kwargs['episode.index'] = episode_number
        if media_content_type == MEDIA_TYPE_MOVIE:
            if media_title is not None:
                kwargs['title'] = media_title

        _LOGGER.info(f'Getting library items: {str(kwargs)}')
        media_items = await hass.loop.run_in_executor(
            None,
            functools.partial(
                plex_server_library.search,
                **{k: v for k, v in kwargs.items() if v is not None}
            )
        )
        # media_items = await _search_library(
        #     plex_server_library,
        #     libtype=media_content_type,
        #     title=media_title,
        #     grandparentTitle=show_name,
        #     index=episode_number if show_name is not None else None,
        #     parentIndex=season_number if show_name is not None else None
        # )
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

    def _get_plex_server_by_name(
            server_name: str = None
    ) -> Optional[PlexServer]:
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

        return matching_plex_servers[0]

    # async def _get_library_items_of_type(
    #         plex_server_library: Library,
    #         media_content_type: str
    # ):
    #     results = await hass.async_add_executor_job(plex_server_library.search, None, media_content_type.lower())
    #     matching_items = [
    #         item for
    #         item
    #         in results
    #         if item.TYPE.lower() == media_content_type.lower()
    #     ]
    #
    #     if not matching_items:
    #         _LOGGER.error(
    #             "Requested content type '%s' not found in %s",
    #             media_content_type.lower(),
    #             [
    #                 library_section.lower()
    #                 for library_section
    #                 in plex_server_library.library.sections()
    #             ]
    #         )
    #         return None
    #
    #     return matching_items

    # def _filter_items_by_genre(
    #         media_items,
    #         genres
    # ):
    #     if not genres:
    #         _LOGGER.error(
    #             "No genres specified to filter by"
    #         )
    #         return media_items
    #
    #     matching_items = [
    #         item
    #         for item
    #         in media_items
    #         if hasattr(item, 'genres') and len([
    #             genre
    #             for genre
    #             in genres
    #             if [fuzz.WRatio(
    #                 item.genre.lower(),  # re.sub(NON_ALPHA_NUMERIC_REGEX_PATTERN, "", media_title).lower(),
    #                 genre.title.lower(),  # re.sub(NON_ALPHA_NUMERIC_REGEX_PATTERN, "", item.title).lower(),
    #                 full_process=True
    #             ) > 95]]) > 0
    #     ]
    #
    #     if not matching_items:
    #         _LOGGER.error(
    #             "No items match the specified genres %s",
    #             genres
    #         )
    #         return None
    #
    #     return matching_items

    # def _filter_items_by_title(
    #         media_items,
    #         media_title
    # ):
    #     from fuzzywuzzy import fuzz
    #
    #     _LOGGER.info('Performing fuzzy match')
    #     matching_items = [
    #         {
    #             "media_item": item,
    #             "match": fuzz.WRatio(
    #                 media_title.lower(),  # re.sub(NON_ALPHA_NUMERIC_REGEX_PATTERN, "", media_title).lower(),
    #                 item.title.lower(),  # re.sub(NON_ALPHA_NUMERIC_REGEX_PATTERN, "", item.title).lower(),
    #                 full_process=True
    #             )
    #         }
    #         for item
    #         in media_items
    #     ]
    #
    #     if not matching_items:
    #         _LOGGER.error(
    #             "Unable to find any items with title close to %s",
    #             media_title
    #         )
    #         return None
    #
    #     _LOGGER.info('Sorting')
    #     return [item['media_item'] for item in sorted(matching_items, key=lambda item: item['match'], reverse=True)]

    async def _search_and_play(service):
        entity_id = service.data.get(ATTR_ENTITY_ID)
        media_content_type = service.data.get(ATTR_MEDIA_CONTENT_TYPE)
        server_name = service.data.get(ATTR_SERVER_NAME, conf.get(CONF_DEFAULT_SERVER_NAME, None))
        show_name = service.data.get(ATTR_SHOW_NAME, None)
        media_title = service.data.get(ATTR_MEDIA_TITLE, None)
        pick_random = service.data.get(ATTR_PICK_RANDOM, False)
        season = service.data.get(ATTR_SEASON_NUMBER, None)
        episode = service.data.get(ATTR_EPISODE_NUMBER, None)

        plex_server = _get_plex_server_by_name(server_name)
        if not plex_server:
            _LOGGER.error('Unable to lookup server by name %s', server_name)
            return

        entity_registry = await get_entity_registry(hass)
        entity_entry = entity_registry.async_get(entity_id)
        if not entity_entry:
            _LOGGER.error('Unable to lookup entity from registry with entity id of %s', entity_id)
            return
        device_registry = await get_device_registry(hass)
        device_entry = device_registry.async_get(entity_entry.device_id)
        if not device_entry:
            _LOGGER.error('Unable to lookup device from registry with device id of %s', entity_entry.device_id)
            return
        _LOGGER.info('Found device entry: {} {}'.format(device_entry.name, str(device_entry.identifiers)))
        client = None
        for resource in await hass.loop.run_in_executor(None, plex_server.account.resources):
            _LOGGER.info('Resource: {} {} {}'.format(resource.name, resource.clientIdentifier, resource.device))
            if resource.clientIdentifier in list(itertools.chain(*device_entry.identifiers)):
                client = resource
                break
        # clients = [client
        #            for client
        #            in await hass.loop.run_in_executor(None, plex_server.account.resources)
        #            if client.clientIdentifier in device_entry.identifiers]
        if not client:
            _LOGGER.error('Unable to locate linked client')
            return

        await hass.loop.run_in_executor(
            None,
            client.connect
        )

        search_result = await _search(plex_server.library,
                                      media_content_type,
                                      media_title=media_title,
                                      show_name=show_name,
                                      pick_random=pick_random,
                                      season_number=season,
                                      episode_number=episode)

        if not search_result:
            _LOGGER.error("No media items match the search criteria")
            return

        if not search_result.ratingKey:
            _LOGGER.error(
                "Unable to determine the unique identifier for media item %s",
                search_result.title
            )
            return

        _LOGGER.info(f'Invoking service with {search_result}')
        entity = _get_media_player_by_entity_id(
            entity_id
        )
        if not entity:
            return

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
        hass.loop.create_task(_search_and_play(service))
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
