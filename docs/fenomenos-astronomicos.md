# Detecção de Fenômenos Astronômicos

Sistema local (sem dependência de cloud) que detecta fenômenos astronômicos
visíveis a partir da localização do usuário e notifica via
`script.notificacao` quando um evento estiver próximo.

Cobre: eclipses solares e lunares, conjunções e elongações planetárias,
solstícios/equinócios, superluas e picos de chuvas de meteoros (tabela
estática, já que a `astronomy-engine` não tem dados orbitais de detritos).

## Status

**Integração instalável via HACS implementada** (`custom_components/astro_haos/`)
— este é o caminho recomendado. O protótipo inicial em pyscript
(`pyscript/eventos_astronomicos.py` + `packages/astronomia.yaml`) continua no
repositório como referência, mas não é mais necessário se a integração
estiver instalada. Ver [pyscript (legado)](#protótipo-fase-1-pyscript---legado)
no fim deste documento.

Testado ponta a ponta (config flow, coordinator, sensor, notificação,
fallback de localização, options flow) com Home Assistant Core 2024.3 real
e cálculos reais da `astronomy-engine`, fora deste repositório.

## Instalação via HACS

1. Em HACS → menu de três pontos (canto superior direito) → **Repositórios
   customizados** → adicione `https://github.com/gugahdl/Astro-HAOS` com a
   categoria **Integration**.
2. Busque **"Astro HAOS"** na lista de integrações do HACS e instale.
3. Reinicie o Home Assistant (necessário para o HA descobrir o
   `custom_components/astro_haos` novo e instalar a dependência
   `astronomy-engine` pinada no `manifest.json`).
4. Vá em **Configurações → Dispositivos e Serviços → Adicionar integração**,
   busque **"Astro HAOS"** e configure pela UI (ver abaixo).

## Configuração (feita pela UI, sem YAML)

Ao adicionar a integração, você escolhe:

| Campo | Uso |
|---|---|
| **Fonte de localização** | `zone.home` (localização do HA) · GPS de uma pessoa · coordenadas manuais. |
| **Entidade de pessoa** (só se GPS) | Ex: `person.guga`. Se ficar indisponível, cai automaticamente para `zone.home` (log de aviso, sem quebrar). |
| **Latitude/Longitude/Elevação** (só se manual) | Coordenadas fixas, independentes do `zone.home`. |
| **Janela de busca (dias)** | Quantos dias à frente procurar eventos (padrão 90). |
| **Avisar com quantos dias de antecedência** | Quando disparar a notificação (padrão 3). |
| **Serviço de notificação** | `dominio.servico` a chamar — padrão `script.notificacao`, reutilizando o script já existente na sua instalação. |

Tudo isso pode ser alterado depois em **Configurações → Dispositivos e
Serviços → Astro HAOS → Configurar** (options flow), sem precisar remover e
reinstalar a integração.

**Confira os nomes dos campos** que o seu `script.notificacao` espera. A
integração chama esse serviço com `titulo` e `mensagem` — se os nomes forem
diferentes, ajuste em `custom_components/astro_haos/coordinator.py`, método
`_notificar_evento`.

## Uso

- `sensor.proximo_evento_astronomico` é criado automaticamente.
- A busca roda uma vez ao configurar, depois todo dia às 6h (e também a
  cada 24h como rede de segurança, caso o HA reinicie em outro horário).
- Para forçar uma busca imediata: **Developer Tools → Ações →
  `astro_haos.buscar_eventos`**, ou o botão "Atualizar" da própria entidade.
- Deduplicação de notificações é persistida via `homeassistant.helpers.storage.Store`
  (arquivo em `.storage/`, não precisa cuidar manualmente).

## sensor.proximo_evento_astronomico

- **Estado**: nome do próximo evento (ex: `Eclipse Solar Partial`,
  `Superlua`, `Conjunção Venus-Jupiter`).
- **Atributos**:
  - `data_hora` — horário local do evento.
  - `dias_restantes`
  - `visibilidade` — texto descritivo (ex: se um eclipse lunar não é
    visível localmente porque a lua está abaixo do horizonte no pico).
  - `obscuracao_percentual` — só preenchido para eclipses.
  - `fonte_localizacao` — `manual`, `gps_person` ou `zone_home`, útil para
    depuração.
  - `janela_busca_dias`
  - `proximos_eventos` — lista com até 15 próximos eventos na janela,
    cada um com os mesmos campos acima.
  - `ultima_atualizacao`

## Limitações conhecidas

- Conjunções planetárias são detectadas por varredura diária de
  separação angular (`PairLongitude`), não por busca binária exata —
  suficiente para notificação com 1 dia de antecedência, mas o horário
  exato do pico pode ter um pequeno erro.
- Chuvas de meteoros usam uma tabela estática de picos conhecidos
  (Perseidas, Geminídeas etc.) sem ajuste por hemisfério ou fase da lua —
  o campo `visibilidade` deixa isso explícito no texto.
- Eclipses penumbrais são ignorados de propósito (pouco perceptíveis a
  olho nu).
- Só uma instância da integração é permitida (não faz sentido ter duas
  rodando a mesma busca).

## Protótipo Fase 1 (pyscript) - legado

Antes de virar uma integração de verdade, a lógica foi validada como script
pyscript solto (`pyscript/eventos_astronomicos.py` +
`packages/astronomia.yaml`, com helpers `input_boolean`/`input_number`).
Os dois caminhos calculam os mesmos eventos com a mesma biblioteca — não
faz sentido rodar os dois ao mesmo tempo (duplicaria notificações). Se você
já tinha instalado a versão pyscript, remova os arquivos de `/config/pyscript/`
e `/config/packages/` e os helpers correspondentes antes de instalar a
integração via HACS.

## Fase 2 (não implementada)

Migrar para um addon dedicado (mesmo padrão do addon Flask do Deco S7
MQTT já existente), publicando os sensores via MQTT Discovery em vez de
manter o cálculo dentro do processo do HA. Com a integração via HACS já
rodando o cálculo isolado do processo principal do jeito idiomático do HA
(coordinator com `async_add_executor_job`), a motivação original para essa
fase (desacoplar do HA core) fica bem menos forte — só vale revisitar se a
integração se mostrar pesada demais para a RPi4 em produção.
