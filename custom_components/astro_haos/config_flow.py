"""Config flow da integração Astro HAOS."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SelectOptionDict,
)

from .const import (
    CONF_ELEVATION,
    CONF_LATITUDE,
    CONF_LOCATION_SOURCE,
    CONF_LONGITUDE,
    CONF_NOTIFY_SERVICE,
    CONF_PERSON_ENTITY,
    CONF_SEARCH_WINDOW_DAYS,
    CONF_WARNING_WINDOW_DAYS,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_SEARCH_WINDOW_DAYS,
    DEFAULT_WARNING_WINDOW_DAYS,
    DOMAIN,
    LOCATION_SOURCE_MANUAL,
    LOCATION_SOURCE_PERSON,
    LOCATION_SOURCE_ZONE_HOME,
)


def _schema_principal(hass: HomeAssistant, defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_LOCATION_SOURCE,
            default=defaults.get(CONF_LOCATION_SOURCE, LOCATION_SOURCE_ZONE_HOME),
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=LOCATION_SOURCE_ZONE_HOME, label="Localização do Home Assistant (zone.home)"),
                    SelectOptionDict(value=LOCATION_SOURCE_PERSON, label="GPS de uma pessoa"),
                    SelectOptionDict(value=LOCATION_SOURCE_MANUAL, label="Coordenadas manuais"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_SEARCH_WINDOW_DAYS,
            default=defaults.get(CONF_SEARCH_WINDOW_DAYS, DEFAULT_SEARCH_WINDOW_DAYS),
        ): NumberSelector(NumberSelectorConfig(min=7, max=365, step=1, mode=NumberSelectorMode.BOX)),
        vol.Required(
            CONF_WARNING_WINDOW_DAYS,
            default=defaults.get(CONF_WARNING_WINDOW_DAYS, DEFAULT_WARNING_WINDOW_DAYS),
        ): NumberSelector(NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX)),
        vol.Required(
            CONF_NOTIFY_SERVICE,
            default=defaults.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
        ): str,
    })


def _schema_manual(hass: HomeAssistant, defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_LATITUDE, default=defaults.get(CONF_LATITUDE, hass.config.latitude)
        ): NumberSelector(NumberSelectorConfig(min=-90, max=90, step=0.0001, mode=NumberSelectorMode.BOX)),
        vol.Required(
            CONF_LONGITUDE, default=defaults.get(CONF_LONGITUDE, hass.config.longitude)
        ): NumberSelector(NumberSelectorConfig(min=-180, max=180, step=0.0001, mode=NumberSelectorMode.BOX)),
        vol.Required(
            CONF_ELEVATION, default=defaults.get(CONF_ELEVATION, hass.config.elevation)
        ): NumberSelector(NumberSelectorConfig(min=-500, max=9000, step=1, mode=NumberSelectorMode.BOX)),
    })


def _schema_person(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_PERSON_ENTITY, default=defaults.get(CONF_PERSON_ENTITY)
        ): EntitySelector(EntitySelectorConfig(domain="person")),
    })


class AstroHaosConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Fluxo de configuração inicial (só permite uma instância)."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            self._data.update(user_input)
            if user_input[CONF_LOCATION_SOURCE] == LOCATION_SOURCE_MANUAL:
                return await self.async_step_manual()
            if user_input[CONF_LOCATION_SOURCE] == LOCATION_SOURCE_PERSON:
                return await self.async_step_person()
            return self.async_create_entry(title="Astronomia", data=self._data)

        return self.async_show_form(
            step_id="user", data_schema=_schema_principal(self.hass, {})
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="Astronomia", data=self._data)
        return self.async_show_form(
            step_id="manual", data_schema=_schema_manual(self.hass, {})
        )

    async def async_step_person(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="Astronomia", data=self._data)
        return self.async_show_form(
            step_id="person", data_schema=_schema_person({})
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "AstroHaosOptionsFlow":
        return AstroHaosOptionsFlow(config_entry)


class AstroHaosOptionsFlow(config_entries.OptionsFlow):
    """Permite reconfigurar localização e janelas depois da instalação."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._data: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        atuais = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_LOCATION_SOURCE] == LOCATION_SOURCE_MANUAL:
                return await self.async_step_manual()
            if user_input[CONF_LOCATION_SOURCE] == LOCATION_SOURCE_PERSON:
                return await self.async_step_person()
            return self.async_create_entry(title="", data=self._data)

        return self.async_show_form(
            step_id="init", data_schema=_schema_principal(self.hass, atuais)
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None):
        atuais = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)
        return self.async_show_form(
            step_id="manual", data_schema=_schema_manual(self.hass, atuais)
        )

    async def async_step_person(self, user_input: dict[str, Any] | None = None):
        atuais = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)
        return self.async_show_form(
            step_id="person", data_schema=_schema_person(atuais)
        )
