# Preparação para IA (previsão e sugestões)

Nesta fase existe **só a estrutura**: nenhum modelo foi implementado e nenhuma tabela foi criada.

## O que existe hoje (`backend/app/analytics/`)
- `protocolos.py`: interfaces `Protocol` (verificáveis com `isinstance`):
  - `FeatureBuilder.construir(dados, data_referencia) -> DataFrame`: monta features só com dados até a data de referência (sem olhar o futuro);
  - `Predictor` (`nome`, `versao`, `treinar`, `prever`): devolve uma lista de `Previsao`;
  - `Strategy` (`nome`, `versao`, `sugerir`): transforma previsões e a carteira em `Sugestao`. **Nunca executa nada sozinha**;
  - `Backtester.executar(modelo, dados, inicio, fim) -> ResultadoBacktest`.
- `registry.py`: `RegistroModelos`:
  - registra modelos por `(nome, versão)` (`MAJOR.MINOR.PATCH`, comparada numericamente);
  - entrega a versão pedida ou a mais recente;
  - guarda uma **fábrica** que só roda quando o modelo é pedido. O registro global `REGISTRO_MODELOS` está vazio.

## Dependências pesadas continuam opcionais
1. O executável atual só depende de pandas (já usado pela série de patrimônio). scikit-learn, statsmodels, PyTorch etc. **não** entram em `dependencies`.
2. Quando houver modelos, eles entram como extra opcional no `pyproject.toml` (ex.: `[project.optional-dependencies] ml = [...]`). O build padrão (Parte 5) não instala o extra.
3. Cada implementação importa a biblioteca pesada **dentro da fábrica**, nunca no topo do módulo. Se a biblioteca não estiver instalada, `RegistroModelos.obter` levanta `ModeloIndisponivelError` com mensagem em pt-BR e o resto do app segue normalmente (há teste para isso).
4. Artefatos treinados ficam em `%APPDATA%\Financas\models\` (`core/paths.diretorio_models`), nunca na pasta de instalação, com nome `<modelo>-<versao>.<ext>` e um arquivo JSON de metadados ao lado (data de treino, features, métricas).
5. Treinos e backtests rodam fora da thread da API (job em segundo plano), para a UI não travar.

## Plano das tabelas futuras (não criadas)
Serão criadas por uma migração Alembic própria quando a funcionalidade for priorizada.

### `previsoes`
| coluna | tipo | observação |
|---|---|---|
| id | inteiro PK | |
| modelo | texto | nome no registry |
| versao | texto | versão do modelo que gerou |
| alvo | texto | ex.: `ativo:12:preco`, `carteira:patrimonio` |
| ativo_id | FK `ativos` (nulo) | quando o alvo é um ativo |
| data_referencia | data | quando a previsão foi feita |
| data_alvo | data | a que dia se refere |
| valor | texto decimal | nunca float |
| limite_inferior / limite_superior | texto decimal (nulo) | intervalo de confiança |
| criado_em | data/hora UTC | |

Índices: `(alvo, data_alvo)` e `(modelo, versao, data_referencia)`. Única: `(modelo, versao, alvo, data_referencia, data_alvo)`.

### `sugestoes`
| coluna | tipo | observação |
|---|---|---|
| id | inteiro PK | |
| estrategia | texto | nome no registry |
| versao | texto | |
| data_referencia | data | |
| acao | texto | ex.: `aportar`, `rebalancear`, `manter` |
| ativo_id | FK `ativos` (nulo) | |
| justificativa | texto | em pt-BR, exibida ao usuário |
| confianca | texto decimal (nulo) | razão de 0 a 1 |
| detalhes | JSON | parâmetros da sugestão |
| status | texto | `nova`, `vista`, `descartada`, `aplicada_manual` |
| criado_em | data/hora UTC | |

Índice: `(data_referencia, status)`.

Sugestões são **apenas informativas**: o app nunca executa ordens nem altera transações a partir delas.
