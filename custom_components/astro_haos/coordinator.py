"""Coordinator: busca periódica dos fenômenos astronômicos e notificação."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .astronomia import calcular_todos_eventos
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
    MAX_NOTIFICADOS_GUARDADOS,
    STORAGE_VERSION,
    UPDATE_INTERVAL_HOURS,
    get_config,
)

_LOGGER = logging.getLogger(__name__)


class AstroHaosCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Busca os próximos fenômenos astronômicos e dispara notificações."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
        )
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.notificados")
        self._notificados: set[str] | None = None

    async def _async_carregar_notificados(self) -> set[str]:
        if self._notificados is None:
            dados = await self._store.async_load()
            self._notificados = set(dados or [])
        return self._notificados

    async def _resolver_localizacao(self) -> tuple[float, float, float, str]:
        fonte = get_config(self.entry, CONF_LOCATION_SOURCE)

        if fonte == LOCATION_SOURCE_MANUAL:
            return (
                get_config(self.entry, CONF_LATITUDE, self.hass.config.latitude),
                get_config(self.entry, CONF_LONGITUDE, self.hass.config.longitude),
                get_config(self.entry, CONF_ELEVATION, self.hass.config.elevation),
                "manual",
            )

        if fonte == LOCATION_SOURCE_PERSON:
            entity_id = get_config(self.entry, CONF_PERSON_ENTITY)
            state = self.hass.states.get(entity_id) if entity_id else None
            if state and "latitude" in state.attributes and "longitude" in state.attributes:
                return (
                    state.attributes["latitude"],
                    state.attributes["longitude"],
                    self.hass.config.elevation,
                    "gps_person",
                )
            _LOGGER.warning(
                "Localização de %s indisponível, usando zone.home como fallback", entity_id
            )

        return (
            self.hass.config.latitude,
            self.hass.config.longitude,
            self.hass.config.elevation,
            "zone_home",
        )

    async def _notificar_evento(self, evento: dict) -> None:
        notify_service = get_config(self.entry, CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)
        if "." not in notify_service:
            _LOGGER.error(
                "notify_service '%s' inválido - use o formato dominio.servico (ex: script.notificacao)",
                notify_service,
            )
            return
        dominio, servico = notify_service.split(".", 1)

        titulo = f"Fenômeno astronômico: {evento['tipo']}"
        partes = [f"Em {evento['dias_restantes']} dia(s), {evento['data_hora_local']}."]
        if evento.get("obscuracao") is not None:
            partes.append(f"Obscuração: {evento['obscuracao']}%.")
        if evento.get("visibilidade"):
            partes.append(evento["visibilidade"] + ".")
        mensagem = " ".join(partes)

        # Ajuste os nomes dos campos (titulo/mensagem) se o seu
        # script.notificacao usar `fields` diferentes.
        try:
            await self.hass.services.async_call(
                dominio, servico, {"titulo": titulo, "mensagem": mensagem}, blocking=True
            )
        except Exception as err:
            _LOGGER.error("Falha ao chamar %s: %s", notify_service, err)

    async def _async_update_data(self) -> dict[str, Any]:
        lat, lon, elevacao, fonte = await self._resolver_localizacao()
        janela_busca = get_config(self.entry, CONF_SEARCH_WINDOW_DAYS, DEFAULT_SEARCH_WINDOW_DAYS)
        janela_aviso = get_config(self.entry, CONF_WARNING_WINDOW_DAYS, DEFAULT_WARNING_WINDOW_DAYS)

        eventos = await self.hass.async_add_executor_job(
            calcular_todos_eventos, lat, lon, elevacao, janela_busca
        )

        agora_utc = dt_util.utcnow()
        for evento in eventos:
            dt_evento = dt_util.parse_datetime(evento["data_hora"])
            evento["dias_restantes"] = round((dt_evento - agora_utc).total_seconds() / 86400, 1)
            evento["data_hora_local"] = dt_util.as_local(dt_evento).isoformat()

        notificados = await self._async_carregar_notificados()
        houve_notificacao_nova = False
        for evento in eventos:
            dentro_da_janela = 0 <= evento["dias_restantes"] <= janela_aviso
            chave = f"{evento['tipo']}|{evento['data_hora']}"
            if dentro_da_janela and chave not in notificados:
                await self._notificar_evento(evento)
                notificados.add(chave)
                houve_notificacao_nova = True

        if houve_notificacao_nova:
            if len(notificados) > MAX_NOTIFICADOS_GUARDADOS:
                notificados = set(list(notificados)[-MAX_NOTIFICADOS_GUARDADOS:])
                self._notificados = notificados
            await self._store.async_save(list(notificados))

        return {
            "eventos": eventos,
            "fonte_localizacao": fonte,
            "janela_busca_dias": janela_busca,
            "ultima_atualizacao": dt_util.now().isoformat(),
        }
