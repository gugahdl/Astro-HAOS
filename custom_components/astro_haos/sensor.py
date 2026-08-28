"""Sensor com o próximo fenômeno astronômico."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AstroHaosCoordinator

MAX_EVENTOS_NO_ATRIBUTO = 15


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AstroHaosCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ProximoEventoAstronomicoSensor(coordinator, entry)])


class ProximoEventoAstronomicoSensor(CoordinatorEntity[AstroHaosCoordinator], SensorEntity):
    """sensor.proximo_evento_astronomico."""

    _attr_name = "Próximo evento astronômico"
    _attr_icon = "mdi:telescope"

    def __init__(self, coordinator: AstroHaosCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_proximo_evento"
        self.entity_id = "sensor.proximo_evento_astronomico"

    @property
    def native_value(self) -> str:
        eventos = (self.coordinator.data or {}).get("eventos", [])
        return eventos[0]["tipo"] if eventos else "Nenhum evento na janela"

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        eventos = data.get("eventos", [])
        proximo = eventos[0] if eventos else {}
        return {
            "data_hora": proximo.get("data_hora_local"),
            "dias_restantes": proximo.get("dias_restantes"),
            "visibilidade": proximo.get("visibilidade"),
            "obscuracao_percentual": proximo.get("obscuracao"),
            "fonte_localizacao": data.get("fonte_localizacao"),
            "janela_busca_dias": data.get("janela_busca_dias"),
            "proximos_eventos": eventos[:MAX_EVENTOS_NO_ATRIBUTO],
            "ultima_atualizacao": data.get("ultima_atualizacao"),
        }
