# Detecção de Fenômenos Astronômicos

Sistema local (sem dependência de cloud) que detecta fenômenos astronômicos
visíveis a partir da localização do usuário e notifica via
`script.notificacao` quando um evento estiver próximo.

Cobre: eclipses solares e lunares, conjunções e elongações planetárias,
solstícios/equinócios, superluas e picos de chuvas de meteoros (tabela
estática, já que a `astronomy-engine` não tem dados orbitais de detritos).

## Status

**Fase 1 (validação via pyscript) implementada.** Fase 2 (addon dedicado
com MQTT Discovery) ainda não foi iniciada — só faz sentido depois da
Fase 1 rodar em produção sem problemas.

## Arquivos

- `pyscript/eventos_astronomicos.py` — toda a lógica de cálculo e o
  serviço `pyscript.buscar_eventos_astronomicos`.
- `packages/astronomia.yaml` — helpers (`input_boolean`/`input_number`/
  `input_text`) usados para configurar localização e janelas de tempo.

## Pré-requisitos

1. Integração **pyscript** instalada via HACS.
2. Pacote `packages` habilitado em `configuration.yaml`:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

3. `script.notificacao` já existente na instalação (não é criado por este
   projeto — é reutilizado). **Confira os nomes dos campos** que esse
   script espera (`titulo`/`mensagem` ou outros) e ajuste a chamada em
   `_notificar_evento()` no final de `pyscript/eventos_astronomicos.py`
   se forem diferentes.

## Instalação

1. Copie `pyscript/eventos_astronomicos.py` para `/config/pyscript/`.
2. Copie `packages/astronomia.yaml` para `/config/packages/`.
3. Reinicie o Home Assistant (ou recarregue pyscript + YAML) para que:
   - o pyscript baixe `astronomy-engine` no seu venv isolado (primeira
     carga pode demorar um pouco na RPi4);
   - os helpers do pacote sejam criados.
4. Em **Developer Tools → Ações**, chame `pyscript.buscar_eventos_astronomicos`
   manualmente e confira:
   - `sensor.proximo_evento_astronomico` foi criado/atualizado;
   - o atributo `proximos_eventos` tem uma lista plausível de eventos;
   - nenhum erro apareceu no log (`Configurações → Sistema → Logs`,
     filtrar por `pyscript.eventos_astronomicos`).
5. Só depois de validar o passo 4 algumas vezes, deixe o
   `@time_trigger("cron(0 6 * * *)")` rodar sozinho — ele já está ativo
   assim que o arquivo é carregado, mas o disparo diário só importa de
   fato depois que a lógica estiver confiável.

## Configuração (helpers criados por `packages/astronomia.yaml`)

| Helper | Uso |
|---|---|
| `input_boolean.astro_localizacao_manual` | Se ligado, usa lat/lon/elevação manuais abaixo (maior prioridade). |
| `input_number.astro_latitude_manual` / `astro_longitude_manual` / `astro_elevacao_manual` | Coordenadas manuais, usadas só quando o toggle acima está ligado. |
| `input_boolean.astro_usar_gps_person` | Se ligado (e o toggle manual desligado), usa a localização de `person.guga`. Se o GPS estiver indisponível, cai automaticamente para `zone.home`. |
| `input_number.astro_janela_busca_dias` | Quantos dias à frente buscar eventos (padrão 90). |
| `input_number.astro_janela_aviso_dias` | Quantos dias antes de um evento a notificação deve disparar (padrão 3). |
| `input_text.astro_eventos_notificados_ids` | Uso interno — evita notificar o mesmo evento repetidamente a cada execução diária. Não editar manualmente. |

Prioridade de localização: **manual > GPS de `person.guga` > `zone.home`**
(via `hass.config.latitude/longitude/elevation`, que é a mesma fonte que
alimenta `zone.home`).

## sensor.proximo_evento_astronomico

- **Estado**: nome do próximo evento (ex: `Eclipse Solar Partial`,
  `Superlua`, `Conjunção Venus-Jupiter`).
- **Atributos**:
  - `data_hora` — horário local (timezone `America/Sao_Paulo`) do evento.
  - `dias_restantes`
  - `visibilidade` — texto descritivo (ex: se um eclipse lunar não é
    visível localmente porque a lua está abaixo do horizonte no pico).
  - `obscuracao_percentual` — só preenchido para eclipses.
  - `fonte_localizacao` — `manual`, `gps_person` ou `zone_home`, útil para
    depuração.
  - `proximos_eventos` — lista com até 15 próximos eventos na janela,
    cada um com os mesmos campos acima.

## Limitações conhecidas (Fase 1)

- Conjunções planetárias são detectadas por varredura diária de
  separação angular (`PairLongitude`), não por busca binária exata —
  suficiente para notificação com 1 dia de antecedência, mas o horário
  exato do pico pode ter um pequeno erro.
- Chuvas de meteoros usam uma tabela estática de picos conhecidos
  (Perseidas, Geminídeas etc.) sem ajuste por hemisfério ou fase da lua —
  o campo `visibilidade` deixa isso explícito no texto.
- Eclipses penumbrais são ignorados de propósito (pouco perceptíveis a
  olho nu).
- Sem deduplicação entre execuções manuais de teste e o cron diário além
  do que já está em `input_text.astro_eventos_notificados_ids` — rodar o
  serviço manualmente várias vezes seguidas não duplica notificações para
  o mesmo evento.

## Fase 2 (não implementada)

Migrar para um addon dedicado (mesmo padrão do addon Flask do Deco S7
MQTT já existente), publicando os sensores via MQTT Discovery em vez de
manter o cálculo dentro do processo do HA. Só faz sentido revisitar depois
da Fase 1 validada em produção.
