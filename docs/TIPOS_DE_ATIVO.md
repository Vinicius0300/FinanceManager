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
- `provider`: só o **nome** da fonte de cotação (os providers chegam na Parte 3);
- `campos`: tupla de `CampoEspecifico` (texto, decimal, inteiro, data ou escolha), com rótulo, ajuda, obrigatoriedade, opções e limites. `schema()` devolve tudo em JSON para gerar o formulário no front;
- `tipos_transacao`: as transações aceitas;
- `regras_adicionais(metadados)`: validações que envolvem mais de um campo, com mensagens em pt-BR;
- `validar_transacao(...)`: regras extras por transação (ex.: aporte depois do vencimento);
- `indicadores_necessarios(metadados)`: o que a atualização da Parte 3 precisa buscar;
- `tolerancia_defasagem` (cotados): idade máxima do preço antes de marcá-lo como defasado.

A validação genérica (`validar_metadados`) cobre:
- campo desconhecido;
- campo obrigatório ausente;
- tipo, intervalo, tamanho e opção inválidos.

Os metadados normalizados são gravados em JSON: decimais e datas como texto, nunca `float`.

## Tipos atuais

| slug | Base | Moedas | Provider | Campos específicos | Transações |
|---|---|---|---|---|---|
| `acao_br` | Cotado | BRL | yfinance | tipo de papel (opcional), setor (opcional) | compra, venda, provento |
| `acao_us` | Cotado | USD | yfinance | bolsa (opcional) | compra, venda, provento |
| `fundo` | Cotado | BRL | cvm | CNPJ (obrigatório, dígitos verificados), classe | compra, venda, provento |
| `cripto` | Cotado | BRL, USD | coingecko | nenhum | compra, venda |
| `renda_fixa` | Montante | BRL | nenhum (CDI/IPCA dos indicadores) | indexador, taxa, aplicação, vencimento, emissor, liquidez | aporte, resgate |
| `poupanca` | Montante | BRL | nenhum (Selic dos indicadores) | nenhum | aporte, resgate |

## Como criar um 7º tipo (exemplo: fundo imobiliário)
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

   O teste `test_setimo_tipo_entra_sem_alterar_os_existentes` (em `tests/test_tipos_de_ativo.py`) usa exatamente esta classe e confere que os schemas dos outros seis tipos não mudam.
4. Não precisa migração nem mudança nos services: compra, venda, provento, eventos, caixa, avaliação e série de patrimônio já funcionam pelo modo `cotas`.

Um tipo **sem cotação pública** (ex.: imóvel) pode herdar de `HandlerCotado` com quantidade 1 e preços `manual`. Um tipo com **rendimento calculado** (ex.: debênture) herda de `HandlerMontante` e implementa `criar_fator`.
