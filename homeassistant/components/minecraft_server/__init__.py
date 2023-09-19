"""The Minecraft Server integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er

from .const import DOMAIN, KEY_LATENCY, KEY_MOTD
from .coordinator import MinecraftServerCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Minecraft Server from a config entry."""
    _LOGGER.debug(
        "Creating coordinator instance for '%s' (%s)",
        entry.data[CONF_NAME],
        entry.data[CONF_HOST],
    )

    # Create coordinator instance.
    config_entry_id = entry.entry_id
    coordinator = MinecraftServerCoordinator(hass, config_entry_id, entry.data)
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator instance.
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[config_entry_id] = coordinator

    # Set up platforms.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Minecraft Server config entry."""
    config_entry_id = config_entry.entry_id

    # Unload platforms.
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )

    # Clean up.
    hass.data[DOMAIN].pop(config_entry_id)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry to a new format."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    # 1 --> 2: Use config entry ID as base for unique IDs.
    if config_entry.version == 1:
        old_unique_id = config_entry.unique_id
        assert old_unique_id
        config_entry_id = config_entry.entry_id

        # Migrate config entry.
        _LOGGER.debug("Migrating config entry. Resetting unique ID: %s", old_unique_id)
        config_entry.unique_id = None
        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry)

        # Migrate device.
        await _async_migrate_device_identifiers(hass, config_entry, old_unique_id)

        # Migrate entities.
        await er.async_migrate_entries(hass, config_entry_id, _migrate_entity_unique_id)

    _LOGGER.debug("Migration to version %s successful", config_entry.version)

    return True


async def _async_migrate_device_identifiers(
    hass: HomeAssistant, config_entry: ConfigEntry, old_unique_id: str | None
) -> None:
    """Migrate the device identifiers to the new format."""
    device_registry = dr.async_get(hass)
    device_entry_found = False
    for device_entry in dr.async_entries_for_config_entry(
        device_registry, config_entry.entry_id
    ):
        for identifier in device_entry.identifiers:
            if identifier[1] == old_unique_id:
                # Device found in registry. Update identifiers.
                new_identifiers = {
                    (
                        DOMAIN,
                        config_entry.entry_id,
                    )
                }
                _LOGGER.debug(
                    "Migrating device identifiers from %s to %s",
                    device_entry.identifiers,
                    new_identifiers,
                )
                device_registry.async_update_device(
                    device_id=device_entry.id, new_identifiers=new_identifiers
                )
                # Device entry found. Leave inner for loop.
                device_entry_found = True
                break

        # Leave outer for loop if device entry is already found.
        if device_entry_found:
            break


@callback
def _migrate_entity_unique_id(entity_entry: er.RegistryEntry) -> dict[str, Any]:
    """Migrate the unique ID of an entity to the new format."""

    # Different variants of unique IDs are available in version 1:
    # 1) SRV record: '<host>-srv-<entity_type>'
    # 2) Host & port: '<host>-<port>-<entity_type>'
    # 3) IP address & port: '<mac_address>-<port>-<entity_type>'
    unique_id_pieces = entity_entry.unique_id.split("-")
    entity_type = unique_id_pieces[2]

    # Handle bug in version 1: Entity type names were used instead of
    # keys (e.g. "Protocol Version" instead of "protocol_version").
    new_entity_type = entity_type.lower()
    new_entity_type = new_entity_type.replace(" ", "_")

    # Special case 'MOTD': Name and key differs.
    if new_entity_type == "world_message":
        new_entity_type = KEY_MOTD

    # Special case 'latency_time': Renamed to 'latency'.
    if new_entity_type == "latency_time":
        new_entity_type = KEY_LATENCY

    new_unique_id = f"{entity_entry.config_entry_id}-{new_entity_type}"
    _LOGGER.debug(
        "Migrating entity unique ID from %s to %s",
        entity_entry.unique_id,
        new_unique_id,
    )

    return {"new_unique_id": new_unique_id}
