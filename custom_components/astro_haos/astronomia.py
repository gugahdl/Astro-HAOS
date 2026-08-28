"""Cálculo dos próximos fenômenos astronômicos com astronomy-engine.

Módulo puro (sem dependências do Home Assistant) para poder rodar em
thread via hass.async_add_executor_job - o cálculo é CPU-bound, não deve
bloquear o event loop.
"""

from __future__ import annotations

import logging
from datetime import datetime

import astronomy

_LOGGER = logging.getLogger(__name__)

# Limite de separação angular (graus) para considerar uma conjunção.
LIMIAR_CONJUNCAO_GRAUS = 5.0

# Superlua = lua cheia a até ~1 dia do perigeu, com distância <= 361.000 km
# (definição popular usada pela maioria dos observatórios).
SUPERLUA_DIST_MAX_KM = 361000
SUPERLUA_JANELA_PERIGEU_DIAS = 1.0

# Chuvas de meteoros não têm função dedicada na astronomy-engine (não há
# dados orbitais de detritos). Tabela estática com os picos anuais mais
# conhecidos - datas variam pouco de ano a ano. ZHR = taxa horária zenital
# aproximada; visibilidade real depende do hemisfério e da fase da lua.
CHUVAS_METEOROS = [
    ("Quadrantidas", 1, 4, 120),
    ("Líridas", 4, 22, 18),
    ("Eta Aquáridas", 5, 6, 50),
    ("Perseidas", 8, 12, 100),
    ("Draconídeas", 10, 8, 10),
    ("Oriônidas", 10, 21, 20),
    ("Leônidas", 11, 17, 15),
    ("Geminídeas", 12, 14, 150),
    ("Úrsidas", 12, 22, 10),
]

CORPOS_CONJUNCAO = [
    astronomy.Body.Mercury,
    astronomy.Body.Venus,
    astronomy.Body.Mars,
    astronomy.Body.Jupiter,
    astronomy.Body.Saturn,
]

CORPOS_ELONGACAO = [astronomy.Body.Mercury, astronomy.Body.Venus]


def _time_to_iso_utc(t):
    ano, mes, dia, hora, minuto, segundo = t.Calendar()
    return datetime(ano, mes, dia, hora, minuto, int(segundo)).isoformat() + "+00:00"


def _ano_de(t):
    return t.Calendar()[0]


def _buscar_eclipses_solares(observer, t_agora, limite_ut):
    eventos = []
    try:
        ecl = astronomy.SearchLocalSolarEclipse(t_agora, observer)
    except Exception as err:
        _LOGGER.warning("Falha ao buscar eclipse solar local: %s", err)
        return eventos
    guarda = 0
    while ecl.peak.time.ut <= limite_ut and guarda < 10:
        guarda += 1
        eventos.append({
            "tipo": f"Eclipse Solar {ecl.kind.name}",
            "data_hora": _time_to_iso_utc(ecl.peak.time),
            "obscuracao": round(ecl.obscuration * 100, 1),
            "visibilidade": "Visível localmente",
        })
        ecl = astronomy.NextLocalSolarEclipse(ecl.peak.time, observer)
    return eventos


def _buscar_eclipses_lunares(observer, t_agora, limite_ut):
    eventos = []
    ecl = astronomy.SearchLunarEclipse(t_agora)
    guarda = 0
    while ecl.peak.ut <= limite_ut and guarda < 20:
        guarda += 1
        # Penumbral é pouco perceptível a olho nu - não vale notificação.
        if ecl.kind != astronomy.EclipseKind.Penumbral:
            eq = astronomy.Equator(astronomy.Body.Moon, ecl.peak, observer, True, True)
            hor = astronomy.Horizon(ecl.peak, observer, eq.ra, eq.dec, astronomy.Refraction.Normal)
            visivel = hor.altitude > 0
            eventos.append({
                "tipo": f"Eclipse Lunar {ecl.kind.name}",
                "data_hora": _time_to_iso_utc(ecl.peak),
                "obscuracao": round(ecl.obscuration * 100, 1) if ecl.obscuration else None,
                "visibilidade": (
                    "Visível localmente" if visivel
                    else "Não visível localmente (lua abaixo do horizonte no pico)"
                ),
            })
        ecl = astronomy.NextLunarEclipse(ecl.peak)
    return eventos


def _buscar_solsticios_equinocios(t_agora, limite_ut):
    eventos = []
    nomes = {
        "mar_equinox": "Equinócio de Março",
        "jun_solstice": "Solstício de Junho",
        "sep_equinox": "Equinócio de Setembro",
        "dec_solstice": "Solstício de Dezembro",
    }
    anos = {_ano_de(t_agora), _ano_de(t_agora) + 1}
    for ano in anos:
        estacoes = astronomy.Seasons(ano)
        for atributo, nome in nomes.items():
            tt = getattr(estacoes, atributo)
            if t_agora.ut <= tt.ut <= limite_ut:
                eventos.append({
                    "tipo": nome,
                    "data_hora": _time_to_iso_utc(tt),
                    "obscuracao": None,
                    "visibilidade": "Visível de qualquer lugar (evento global)",
                })
    return eventos


def _buscar_superluas(t_agora, limite_ut):
    eventos = []
    t = t_agora
    guarda = 0
    while guarda < 8:
        guarda += 1
        lua_cheia = astronomy.SearchMoonPhase(180.0, t, 40)
        if lua_cheia is None or lua_cheia.ut > limite_ut:
            break
        apsis = astronomy.SearchLunarApsis(t)
        guarda_apsis = 0
        while (
            apsis.kind != astronomy.ApsisKind.Pericenter
            or abs(apsis.time.ut - lua_cheia.ut) > 25
        ) and guarda_apsis < 4:
            apsis = astronomy.NextLunarApsis(apsis)
            guarda_apsis += 1
        if (
            apsis.kind == astronomy.ApsisKind.Pericenter
            and abs(apsis.time.ut - lua_cheia.ut) <= SUPERLUA_JANELA_PERIGEU_DIAS
            and apsis.dist_km <= SUPERLUA_DIST_MAX_KM
        ):
            eventos.append({
                "tipo": "Superlua",
                "data_hora": _time_to_iso_utc(lua_cheia),
                "obscuracao": None,
                "visibilidade": f"Distância ao perigeu: {round(apsis.dist_km)} km",
            })
        t = lua_cheia.AddDays(20)
    return eventos


def _buscar_conjuncoes(t_agora, janela_dias, limite_ut):
    eventos = []
    passo_dias = 1.0
    n_passos = max(int(janela_dias / passo_dias), 1)
    pares = [
        (a, b)
        for i, a in enumerate(CORPOS_CONJUNCAO)
        for b in CORPOS_CONJUNCAO[i + 1:]
    ]
    for corpo1, corpo2 in pares:
        serie = []
        for i in range(n_passos + 1):
            t = t_agora.AddDays(i * passo_dias)
            lon = astronomy.PairLongitude(corpo1, corpo2, t)
            diferenca = min(lon, 360.0 - lon)
            serie.append((t, diferenca))
        for i in range(1, len(serie) - 1):
            _, dif_ant = serie[i - 1]
            t_atual, dif_atual = serie[i]
            _, dif_prox = serie[i + 1]
            if dif_atual <= LIMIAR_CONJUNCAO_GRAUS and dif_atual <= dif_ant and dif_atual <= dif_prox:
                eventos.append({
                    "tipo": f"Conjunção {corpo1.name}-{corpo2.name}",
                    "data_hora": _time_to_iso_utc(t_atual),
                    "obscuracao": None,
                    "visibilidade": f"Separação aproximada: {round(dif_atual, 1)}°",
                })
    return eventos


def _buscar_elongacoes(t_agora, limite_ut):
    eventos = []
    for corpo in CORPOS_ELONGACAO:
        t = t_agora
        guarda = 0
        while guarda < 4:
            guarda += 1
            evento = astronomy.SearchMaxElongation(corpo, t)
            if evento is None or evento.time.ut > limite_ut:
                break
            eventos.append({
                "tipo": f"Máxima Elongação de {corpo.name}",
                "data_hora": _time_to_iso_utc(evento.time),
                "obscuracao": None,
                "visibilidade": (
                    f"{round(evento.elongation, 1)}° do Sol - melhor visto ao "
                    f"{'anoitecer' if evento.visibility == astronomy.Visibility.Evening else 'amanhecer'}"
                ),
            })
            t = evento.time.AddDays(10)
    return eventos


def _buscar_chuvas_meteoros(t_agora, limite_ut):
    eventos = []
    ano_atual = _ano_de(t_agora)
    for nome, mes, dia, zhr in CHUVAS_METEOROS:
        for ano in (ano_atual, ano_atual + 1):
            tt = astronomy.Time.Make(ano, mes, dia, 22, 0, 0)
            if t_agora.ut <= tt.ut <= limite_ut:
                eventos.append({
                    "tipo": f"Chuva de Meteoros: {nome}",
                    "data_hora": _time_to_iso_utc(tt),
                    "obscuracao": None,
                    "visibilidade": f"ZHR aproximado: {zhr}/h (varia com hemisfério e fase da lua)",
                })
    return eventos


def calcular_todos_eventos(lat: float, lon: float, elevacao: float, janela_dias: float) -> list[dict]:
    """Calcula todos os fenômenos astronômicos na janela. Roda em thread."""
    observer = astronomy.Observer(lat, lon, elevacao)
    t_agora = astronomy.Time.Now()
    limite_ut = t_agora.ut + janela_dias

    buscas = [
        ("eclipses solares", lambda: _buscar_eclipses_solares(observer, t_agora, limite_ut)),
        ("eclipses lunares", lambda: _buscar_eclipses_lunares(observer, t_agora, limite_ut)),
        ("solstícios/equinócios", lambda: _buscar_solsticios_equinocios(t_agora, limite_ut)),
        ("superluas", lambda: _buscar_superluas(t_agora, limite_ut)),
        ("conjunções", lambda: _buscar_conjuncoes(t_agora, janela_dias, limite_ut)),
        ("elongações", lambda: _buscar_elongacoes(t_agora, limite_ut)),
        ("chuvas de meteoros", lambda: _buscar_chuvas_meteoros(t_agora, limite_ut)),
    ]

    eventos = []
    for nome, busca in buscas:
        try:
            eventos.extend(busca())
        except Exception as err:
            _LOGGER.error("Falha ao calcular %s: %s", nome, err)

    eventos.sort(key=lambda e: e["data_hora"])
    return eventos
