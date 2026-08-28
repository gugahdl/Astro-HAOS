"""Integração Astro HAOS - detecção de fenômenos astronômicos."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.event import async_track_time_change
from homeassistant.const import Platform

from .const import DAILY_REFRESH_HOUR, DOMAIN, SERVICE_BUSCAR_EVENTOS
from .coordinator import AstroHaosCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AstroHaosCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _atualizar_as_seis_da_manha(_now) -> None:
        await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_change(
            hass, _atualizar_as_seis_da_manha, hour=DAILY_REFRESH_HOUR, minute=0, second=0
        )
    )

    async def _handle_buscar_eventos(_call: ServiceCall) -> None:
        await coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_BUSCAR_EVENTOS):
        hass.services.async_register(DOMAIN, SERVICE_BUSCAR_EVENTOS, _handle_buscar_eventos)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_BUSCAR_EVENTOS)
    return unload_ok
