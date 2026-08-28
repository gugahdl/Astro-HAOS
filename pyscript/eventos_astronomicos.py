# pyscript: requirements: ["astronomy-engine"]
"""
Detecção de fenômenos astronômicos (Fase 1 - validação via pyscript).

Calcula, a partir da localização do observador, os próximos eclipses
solares/lunares, conjunções e elongações planetárias, solstícios/
equinócios, superluas e picos de chuvas de meteoros dentro de uma
janela de dias configurável, publica o resultado em
sensor.proximo_evento_astronomico e dispara script.notificacao quando
um evento estiver dentro da janela de aviso configurada.

Testar manualmente em Developer Tools -> Ações (Services), chamando
pyscript.buscar_eventos_astronomicos, antes de confiar no cron diário.
"""

import logging
from datetime import datetime

import astronomy
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger("pyscript.eventos_astronomicos")

# Valores usados apenas se os helpers em packages/astronomia.yaml
# ainda não tiverem sido criados/carregados.
JANELA_BUSCA_DIAS_PADRAO = 90
JANELA_AVISO_DIAS_PADRAO = 3

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


# ---------------------------------------------------------------------------
# Helpers puros (sem chamadas ao hass) - podem rodar em thread via
# task.executor, já que o cálculo é CPU-bound.
# ---------------------------------------------------------------------------

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


def _calcular_todos_eventos(lat, lon, elevacao, janela_dias):
    """Roda em thread via task.executor - só usa astronomy-engine/stdlib."""
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


# ---------------------------------------------------------------------------
# Helpers que dependem do hass (localização, helpers de configuração,
# deduplicação de notificações). Rodam no contexto normal do pyscript.
# ---------------------------------------------------------------------------

def _numero_helper(entity_id, padrao):
    try:
        return float(state.get(entity_id))
    except Exception:
        return padrao


def _resolver_localizacao():
    """Prioridade: override manual > GPS de person.guga > zone.home."""
    try:
        manual_ligado = state.get("input_boolean.astro_localizacao_manual") == "on"
    except Exception:
        manual_ligado = False

    if manual_ligado:
        lat = _numero_helper("input_number.astro_latitude_manual", hass.config.latitude)
        lon = _numero_helper("input_number.astro_longitude_manual", hass.config.longitude)
        elevacao = _numero_helper("input_number.astro_elevacao_manual", hass.config.elevation)
        return lat, lon, elevacao, "manual"

    try:
        usar_gps = state.get("input_boolean.astro_usar_gps_person") == "on"
    except Exception:
        usar_gps = False

    if usar_gps:
        try:
            lat = float(state.getattr("person.guga")["latitude"])
            lon = float(state.getattr("person.guga")["longitude"])
            return lat, lon, hass.config.elevation, "gps_person"
        except (TypeError, KeyError, ValueError):
            _LOGGER.warning(
                "GPS de person.guga indisponível, usando zone.home como fallback"
            )

    return hass.config.latitude, hass.config.longitude, hass.config.elevation, "zone_home"


def _eventos_ja_notificados():
    try:
        bruto = state.get("input_text.astro_eventos_notificados_ids") or ""
    except Exception:
        bruto = ""
    return set(chave for chave in bruto.split(";") if chave)


def _marcar_notificado(chave):
    atuais = _eventos_ja_notificados()
    atuais.add(chave)
    lista = list(atuais)[-30:]
    texto = ";".join(lista)
    try:
        state.set("input_text.astro_eventos_notificados_ids", texto[:255])
    except Exception as err:
        _LOGGER.warning("Não foi possível gravar dedup de notificações: %s", err)


def _notificar_evento(evento):
    titulo = f"Fenômeno astronômico: {evento['tipo']}"
    partes = [f"Em {evento['dias_restantes']} dia(s), {evento['data_hora_local']}."]
    if evento.get("obscuracao") is not None:
        partes.append(f"Obscuração: {evento['obscuracao']}%.")
    if evento.get("visibilidade"):
        partes.append(evento["visibilidade"] + ".")
    mensagem = " ".join(partes)

    # Ajuste os nomes dos campos (titulo/mensagem) para bater com os
    # `fields` reais definidos em script.notificacao, se forem diferentes.
    service.call("script", "notificacao", titulo=titulo, mensagem=mensagem)


# ---------------------------------------------------------------------------
# Serviço principal + trigger diário
# ---------------------------------------------------------------------------

@service
def buscar_eventos_astronomicos():
    """Busca os próximos fenômenos astronômicos e atualiza o sensor/notifica."""
    lat, lon, elevacao, fonte = _resolver_localizacao()
    janela_dias = _numero_helper("input_number.astro_janela_busca_dias", JANELA_BUSCA_DIAS_PADRAO)
    aviso_dias = _numero_helper("input_number.astro_janela_aviso_dias", JANELA_AVISO_DIAS_PADRAO)

    eventos = task.executor(_calcular_todos_eventos, lat, lon, elevacao, janela_dias)

    agora_utc = dt_util.utcnow()
    for evento in eventos:
        dt_evento = dt_util.parse_datetime(evento["data_hora"])
        evento["dias_restantes"] = round((dt_evento - agora_utc).total_seconds() / 86400, 1)
        evento["data_hora_local"] = dt_util.as_local(dt_evento).isoformat()

    if eventos:
        proximo = eventos[0]
        estado = proximo["tipo"]
        atributos = {
            "data_hora": proximo["data_hora_local"],
            "dias_restantes": proximo["dias_restantes"],
            "visibilidade": proximo["visibilidade"],
            "obscuracao_percentual": proximo["obscuracao"],
        }
    else:
        estado = "Nenhum evento na janela"
        atributos = {
            "data_hora": None,
            "dias_restantes": None,
            "visibilidade": None,
            "obscuracao_percentual": None,
        }

    atributos["fonte_localizacao"] = fonte
    atributos["janela_busca_dias"] = janela_dias
    atributos["proximos_eventos"] = eventos[:15]
    atributos["ultima_atualizacao"] = dt_util.now().isoformat()

    state.set("sensor.proximo_evento_astronomico", estado, atributos)

    ja_notificados = _eventos_ja_notificados()
    for evento in eventos:
        dentro_da_janela = 0 <= evento["dias_restantes"] <= aviso_dias
        chave = f"{evento['tipo']}|{evento['data_hora']}"
        if dentro_da_janela and chave not in ja_notificados:
            _notificar_evento(evento)
            _marcar_notificado(chave)


@time_trigger("cron(0 6 * * *)")
def atualizar_eventos_astronomicos_diario():
    buscar_eventos_astronomicos()
