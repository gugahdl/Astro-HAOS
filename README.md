# Astro HAOS

Integração para Home Assistant que detecta localmente fenômenos
astronômicos visíveis a partir da sua localização — eclipses solares e
lunares, conjunções e elongações planetárias, solstícios/equinócios,
superluas e picos de chuvas de meteoros — e notifica quando um evento
estiver próximo. Cálculo 100% local com [`astronomy-engine`](https://github.com/cosinekitty/astronomy),
sem depender de nenhum serviço externo.

## Instalação (HACS)

1. HACS → menu de três pontos → **Repositórios customizados** → adicione
   este repositório com a categoria **Integration**.
2. Instale **Astro HAOS** pelo HACS e reinicie o Home Assistant.
3. **Configurações → Dispositivos e Serviços → Adicionar integração** →
   busque **Astro HAOS** → configure pela UI.

Detalhes completos, configuração e limitações conhecidas:
[`docs/fenomenos-astronomicos.md`](docs/fenomenos-astronomicos.md).

## Estrutura do repositório

- `custom_components/astro_haos/` — a integração em si (instalável via HACS).
- `pyscript/`, `packages/` — protótipo inicial em pyscript, mantido como
  referência histórica (ver seção "legado" na documentação).
