# Tipos de ativo (registry de handlers)

Cada tipo de ativo é um **handler** isolado em `backend/app/asset_types/`. O slug do handler é gravado em `ativos.tipo` (texto livre, sem CHECK), então **um tipo novo não exige migração nem alteração dos tipos existentes**.

## Contrato (`asset_types/base.py`)
Todo handler herda de uma das duas bases. O registry recusa qualquer outra coisa.

| Base | Modo | Valor atual |
|---|---|---|
| `HandlerCotado` | `cotas` (quantidade × preço) | último preço salvo; sem preço, o custo (defasado) |
| `HandlerMontante` | `montante` (aportes e resgates em R$) | accrual pelo `criar_fator(metadados, indicadores)` |

Cada handler declara:
- `slug`, `nome`, `descricao`;
- `moedas_aceitas` (a primeira é a padrão);
- `provider`: o **nome** da fonte de cotação, igual ao `nome` de um provider registrado em `providers/catalogo.py` (ver seção Providers);
- `campos`: tupla de `CampoEspecifico` (texto, decimal, inteiro, data ou escolha), com rótulo, ajuda, obrigatoriedade, opções e limites. `schema()` devolve tudo em JSON para gerar o formulário no front;
- `tipos_transacao`: as transações aceitas;
- `regras_adicionais(metadados)`: validações que envolvem mais de um campo, com mensagens em pt-BR;
- `validar_transacao(...)`: regras extras por transação (ex.: aporte depois do vencimento);
- `indicadores_necessarios(metadados)`: o que a atualização automática precisa buscar (montante);
- `referencia_indicadores(metadados, data)` (montante): até que data o cálculo usa indicadores (a renda fixa para no vencimento), base do aviso de defasagem;
- `tolerancia_defasagem` (cotados): idade máxima do preço antes de marcá-lo como defasado;
- `agenda`: quando a coleta automática busca a cotação. Padrão `AGENDA_DIARIA`; ações usam `AGENDA_B3`/`AGENDA_EUA` (intervalo configurável, só até o fechamento fora do pregão) e cripto `AGENDA_CONTINUA` (24 h). Ver `domain/agenda.py`;
- `aceita_taxas`: `False` recusa taxas em compra/venda (Tesouro Direto);
- `campos_identificacao`: campos que identificam o ativo **na fonte** (CNPJ do fundo; título e vencimento do Tesouro). Mudá-los na edição apaga os preços automáticos e baixa o histórico de novo.
- `lista_simbolos` (Parte 4.1): lista oficial de tickers usada na busca do cadastro (`"B3"` ou `"EUA"`); `busca_por_ticker` liga a busca por ticker sem lista (cripto, pela pesquisa da CoinGecko);
- `sufixo_simbolo_externo` / `separador_classe`: formato do ticker na fonte (`.SA` dos papéis da B3; `BRK.B` = `BRK-B` nos EUA). `normalizar_simbolo` grava o ticker sem o sufixo e `simbolo_externo_padrao` preenche o símbolo na fonte quando o usuário não informa;
- `mesma_identidade(a, b)` (deduplicação do cadastro): padrão = campos de identificação + símbolo externo; sem eles, o ticker normalizado; montante nunca. Cripto compara o id da CoinGecko (ou o símbolo, se algum ainda não tem id); poupança é sempre o mesmo ativo;
- `semelhante(a, b)`: parece o mesmo investimento sem ser idêntico (o cadastro pergunta). Renda fixa: emissor (sem acento/maiúsculas), indexador, taxa e vencimento.

A validação genérica (`validar_metadados`) cobre:
- campo desconhecido;
- campo obrigatório ausente;
- tipo, intervalo, tamanho e opção inválidos.

Os metadados normalizados são gravados em JSON: decimais e datas como texto, nunca `float`.

## Tipos atuais

| slug | Base | Moedas | Provider | Campos específicos | Transações |
|---|---|---|---|---|---|
| `acao_br` | Cotado | BRL | yfinance | tipo de papel ON/PN/UNIT/BDR (opcional), setor (opcional) | compra, venda, provento |
| `fundo_listado` | Cotado | BRL | yfinance | nenhum (FII, Fiagro, FI-Infra: categoria `FUNDS` da B3) | compra, venda, provento |
| `etf_br` | Cotado | BRL | yfinance | nenhum (ETFs de ações, de índice estrangeiro e de renda fixa) | compra, venda, provento |
| `acao_us` | Cotado | USD | yfinance | bolsa (opcional) | compra, venda, provento |
| `etf_us` | Cotado | USD | yfinance | bolsa (opcional) | compra, venda, provento |
| `fundo` | Cotado | BRL | cvm | CNPJ (obrigatório, dígitos verificados), classe | compra, venda, provento |
| `cripto` | Cotado | BRL, USD | coingecko | nenhum | compra, venda |
| `renda_fixa` | Montante | BRL | nenhum (CDI/IPCA dos indicadores) | indexador, taxa, aplicação, vencimento, emissor, liquidez | aporte, resgate |
| `poupanca` | Montante | BRL | nenhum (Selic dos indicadores) | nenhum | aporte, resgate |
| `tesouro_direto` | Cotado | BRL | tesouro | título (Selic, Prefixado, Prefixado com Juros Semestrais, IPCA+, IPCA+ com Juros Semestrais, Renda+, Educa+) e vencimento | compra, venda, provento (só títulos com juros semestrais); sem taxas |

**Renda fixa × Tesouro Direto:** CDB, LCI, LCA, debêntures e demais títulos privados ficam em `renda_fixa`, com valor estimado por accrual. Títulos do **Tesouro Direto** têm tipo próprio, avaliado pelo **PU de venda** do dia publicado pelo Tesouro Transparente (o valor de resgate antecipado), como uma cota: quantidade × PU. Cupons de juros semestrais entram como provento.

## Providers (fontes de cotação)
Cada fonte é uma classe em `backend/app/providers/` com interface comum (`ProviderCotacao` e/ou `ProviderIndicador`, em `providers/base.py`), registrada em `providers/catalogo.py`. Trocar ou acrescentar uma fonte não altera as outras.

| Provider (`nome`) | Fonte | Tipos | Identificação |
|---|---|---|---|
| `yfinance` | Yahoo Finance (endpoint de gráfico, sem a biblioteca `yfinance`) | `acao_br`, `fundo_listado`, `etf_br`, `acao_us`, `etf_us`; reserva do câmbio | ticker; papéis da B3 ganham `.SA` (gravado em `simbolo_externo` no cadastro); `simbolo_externo` prevalece |
| `coingecko` | CoinGecko (plano público) | `cripto` | tabela embutida (BTC → bitcoin) ou pesquisa (maior valor de mercado); o id é gravado em `simbolo_externo` |
| `tesouro` | Tesouro Transparente (CSV) | `tesouro_direto` | título + vencimento |
| `cvm` | CVM, informe diário (ZIP mensal) | `fundo` | CNPJ; fundo com subclasses usa o id da subclasse em `simbolo_externo` |
| `bcb_sgs` | API SGS do Banco Central | indicadores | séries 4389 (CDI), 432 (Selic meta), 433 (IPCA), 1 (PTAX venda) |

Um tipo novo com cotação precisa de um provider registrado com o mesmo nome do `provider` do handler (o teste `test_tipos_de_ativo_cotados_tem_provider_registrado` confere).

## Como criar um tipo novo (exemplo: fundo imobiliário)
1. Crie `backend/app/asset_types/fii.py`:

```python
"""Fundos imobiliários negociados na B3."""

from typing import ClassVar

from app.asset_types.base import CampoEspecifico, HandlerCotado, Metadados, Opcao, TipoCampo
from app.asset_types.fundo import cnpj_valido
from app.domain.erros import DetalheCampo


class Fii(HandlerCotado):
    slug = "fii"
    nome = "Fundo imobiliário"
    descricao = "Cotas de fundos imobiliários negociadas na B3."
    moedas_aceitas: ClassVar[tuple[str, ...]] = ("BRL",)
    provider = "yfinance"
    campos = (
        CampoEspecifico(
            nome="segmento",
            rotulo="Segmento",
            tipo=TipoCampo.ESCOLHA,
            obrigatorio=False,
            opcoes=(Opcao("logistica", "Logística"), Opcao("papel", "Papel (CRI)")),
        ),
        CampoEspecifico(nome="cnpj", rotulo="CNPJ", tipo=TipoCampo.TEXTO, tamanho_maximo=18),
    )

    def regras_adicionais(self, metadados: Metadados) -> list[DetalheCampo]:
        if cnpj_valido(str(metadados["cnpj"])):
            return []
        return [DetalheCampo("cnpj", "CNPJ inválido.")]
```

2. Registre o handler no **único ponto de registro**, acrescentando `Fii` a `HANDLERS_PADRAO` em `asset_types/catalogo.py`.
3. Escreva os testes:
   - validação: válido, inválido e campos faltando;
   - valor atual conferido à mão;
   - presença do tipo no registry.

   O teste `test_tipo_novo_entra_sem_alterar_os_existentes` (em `tests/test_tipos_de_ativo.py`) usa exatamente esta classe e confere que os schemas dos outros tipos não mudam.
4. Não precisa migração nem mudança nos services: compra, venda, provento, eventos, caixa, avaliação, série de patrimônio e coleta automática (pelo provider `yfinance`, que já existe) funcionam pelo modo `cotas`. Para ser coletado no pregão, declare também `agenda: ClassVar[Agenda] = AGENDA_B3`.

Um tipo **sem cotação pública** (ex.: imóvel) pode herdar de `HandlerCotado` com quantidade 1 e preços `manual`. Um tipo com **rendimento calculado** (ex.: debênture) herda de `HandlerMontante` e implementa `criar_fator`.
