"""Constantes da integração Astro HAOS."""

DOMAIN = "astro_haos"

CONF_LOCATION_SOURCE = "location_source"
LOCATION_SOURCE_ZONE_HOME = "zone_home"
LOCATION_SOURCE_PERSON = "person"
LOCATION_SOURCE_MANUAL = "manual"

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_ELEVATION = "elevation"
CONF_PERSON_ENTITY = "person_entity"
CONF_SEARCH_WINDOW_DAYS = "search_window_days"
CONF_WARNING_WINDOW_DAYS = "warning_window_days"
CONF_NOTIFY_SERVICE = "notify_service"

DEFAULT_SEARCH_WINDOW_DAYS = 90
DEFAULT_WARNING_WINDOW_DAYS = 3
DEFAULT_NOTIFY_SERVICE = "script.notificacao"

UPDATE_INTERVAL_HOURS = 24
DAILY_REFRESH_HOUR = 6

STORAGE_VERSION = 1
MAX_NOTIFICADOS_GUARDADOS = 60

SERVICE_BUSCAR_EVENTOS = "buscar_eventos"


def get_config(entry, key, default=None):
    """Lê uma opção com precedência options > data > padrão."""
    return entry.options.get(key, entry.data.get(key, default))
