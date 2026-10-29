"""Demonstração da Parte 2 em um banco descartável (não toca no %APPDATA% real).

Uso (na raiz do projeto):
    backend\\.venv\\Scripts\\python.exe scripts\\demo_parte2.py

Cria uma pasta temporária, roda as migrações (como o app faz ao abrir), registra o
cenário do prompt (conta RICO, TST11 na RICO e na XP, AAPL em dólar, CDB e uma despesa)
e imprime os números para conferir com docs/CALCULOS.md.
"""

import os
import sys
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
os.environ["FINANCAS_DATA_DIR"] = tempfile.mkdtemp(prefix="financas-demo-")

from app.core import paths  # noqa: E402
from app.core.banco import criar_engine, criar_fabrica_sessoes, sessao_transacional  # noqa: E402
from app.core.migracoes import migrar_banco  # noqa: E402
from app.domain.enums import (  # noqa: E402
    OrigemPreco,
    SubtipoProvento,
    TipoIndicador,
    TipoInstituicao,
    TipoLancamento,
    TipoMovimento,
    TipoTransacao,
)
from app.domain.numeros import arredondar_moeda, percentual  # noqa: E402
from app.services.cadastros import NovoAtivo, criar_ativo, criar_instituicao  # noqa: E402
from app.services.caixa import NovoMovimentoManual, registrar_movimento_manual, saldo  # noqa: E402
from app.services.carteira import avaliar_carteira  # noqa: E402
from app.services.financeiro import (  # noqa: E402
    NovoLancamento,
    criar_categoria,
    obter_resumo_mensal,
    registrar_lancamento,
)
from app.services.mercado import registrar_indicador, registrar_preco  # noqa: E402
from app.services.patrimonio import serie_patrimonio  # noqa: E402
from app.services.transacoes import NovaTransacao, registrar_transacao  # noqa: E402

D = Decimal


def reais(valor: Decimal | None) -> str:
    if valor is None:
        return "indisponível"
    texto = f"{arredondar_moeda(valor):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(razao: Decimal | None) -> str:
    return "indisponível" if razao is None else f"{percentual(razao)}%".replace(".", ",")


def main() -> None:
    paths.garantir_diretorios()
    migrar_banco(paths.caminho_banco(), paths.diretorio_backups())
    engine = criar_engine(paths.caminho_banco())
    fabrica = criar_fabrica_sessoes(engine)
    print(f"Banco de demonstração: {paths.caminho_banco()}\n")

    with sessao_transacional(fabrica) as s:
        rico = criar_instituicao(s, "RICO", TipoInstituicao.CORRETORA)
        xp = criar_instituicao(s, "XP", TipoInstituicao.CORRETORA)
        banco = criar_instituicao(s, "Banco X", TipoInstituicao.BANCO)
        avenue = criar_instituicao(s, "Avenue", TipoInstituicao.CORRETORA)
        tst = criar_ativo(s, NovoAtivo(tipo="acao_br", nome="Teste TST11", simbolo="TST11"))
        aapl = criar_ativo(s, NovoAtivo(tipo="acao_us", nome="Apple", simbolo="AAPL"))
        cdb = criar_ativo(
            s,
            NovoAtivo(
                tipo="renda_fixa",
                nome="CDB Banco X 100% CDI",
                metadados={
                    "indexador": "cdi",
                    "taxa": "100",
                    "data_aplicacao": "2025-08-01",
                    "vencimento": "2030-01-02",
                    "emissor": "Banco X",
                    "liquidez": "diaria",
                },
            ),
        )
        registrar_indicador(s, TipoIndicador.CDI, date(2025, 1, 1), D("14.90"))
        registrar_indicador(s, TipoIndicador.CAMBIO, date(2025, 2, 1), D("5.00"), "USD")
        registrar_indicador(s, TipoIndicador.CAMBIO, date(2025, 9, 1), D("5.50"), "USD")

        def manual(inst_id: int, valor: str, dia: date, moeda: str = "BRL") -> None:
            registrar_movimento_manual(
                s, NovoMovimentoManual(inst_id, moeda, TipoMovimento.DEPOSITO, dia, D(valor))
            )

        def transacao(dados: NovaTransacao, aceitar: bool = False) -> None:
            resultado = registrar_transacao(s, dados, aceitar_ajuste=aceitar)
            if resultado.aviso:
                print(
                    f"AVISO em {dados.data:%d/%m}: {resultado.aviso.mensagem} "
                    f"(faltam {reais(resultado.aviso.valor_faltante)})"
                )
                transacao(dados, aceitar=True)
            elif resultado.ajuste:
                print(f"  -> ajuste de saldo criado: {reais(resultado.ajuste.valor)}")

        def negocio(tipo: TipoTransacao, inst_id: int, dia: date, q: str, p: str) -> NovaTransacao:
            return NovaTransacao(tst.id, inst_id, tipo, dia, quantidade=D(q), preco_unitario=D(p))

        # Tabela do prompt (conta RICO).
        manual(rico.id, "1000", date(2025, 2, 20))
        transacao(negocio(TipoTransacao.COMPRA, rico.id, date(2025, 3, 1), "90", "10"))
        transacao(
            NovaTransacao(
                tst.id,
                rico.id,
                TipoTransacao.PROVENTO,
                date(2025, 3, 10),
                valor=D(45),
                subtipo_provento=SubtipoProvento.DIVIDENDO,
            )
        )
        transacao(negocio(TipoTransacao.VENDA, rico.id, date(2025, 3, 20), "40", "12"))
        transacao(negocio(TipoTransacao.COMPRA, rico.id, date(2025, 3, 25), "70", "11"))
        # Mesmo ativo em outra corretora, AAPL em dólar e um CDB.
        manual(xp.id, "120", date(2025, 3, 1))
        transacao(negocio(TipoTransacao.COMPRA, xp.id, date(2025, 3, 2), "10", "12"))
        manual(avenue.id, "1100", date(2025, 3, 1), "USD")
        transacao(
            NovaTransacao(
                aapl.id,
                avenue.id,
                TipoTransacao.COMPRA,
                date(2025, 3, 2),
                quantidade=D(10),
                preco_unitario=D(100),
                cambio=D(5),
            )
        )
        manual(banco.id, "10000", date(2025, 8, 1))
        transacao(
            NovaTransacao(cdb.id, banco.id, TipoTransacao.APORTE, date(2025, 8, 1), valor=D(10000))
        )
        for ativo, valor in ((tst, "15"), (aapl, "120")):
            registrar_preco(
                s, ativo.id, datetime(2025, 9, 1, 15, tzinfo=UTC), D(valor), OrigemPreco.MANUAL
            )
        mercado = criar_categoria(s, "Mercado", TipoLancamento.DESPESA)
        registrar_lancamento(
            s, NovoLancamento(TipoLancamento.RECEITA, date(2025, 3, 5), "Salário", D(5000))
        )
        registrar_lancamento(
            s,
            NovoLancamento(
                TipoLancamento.DESPESA, date(2025, 3, 12), "Feira", D("349.90"), mercado.id
            ),
        )

    with sessao_transacional(fabrica) as s:
        saldo_rico = saldo(s, rico.id, "BRL", date(2025, 3, 31))
        print(f"\nSaldo da conta RICO em 31/03/2025: {reais(saldo_rico)}")
        carteira = avaliar_carteira(s, date(2025, 9, 1))
        geral = carteira.geral()
        print("\nAnálise Geral em 01/09/2025")
        for posicao in geral.posicoes:
            metricas = posicao.metricas_brl
            rentabilidade = pct(metricas.rentabilidade_total if metricas else None)
            quantidade = "-" if posicao.quantidade is None else posicao.quantidade
            print(
                f"  ativo {posicao.ativo_id} ({posicao.tipo_ativo}): qtd {quantidade}, "
                f"valor {reais(posicao.avaliacao.valor_brl)}, rentabilidade total {rentabilidade}"
            )
        print(
            f"  Investimentos: {reais(geral.investimentos_brl)} | Caixa: {reais(geral.caixa_brl)}"
        )
        print(f"  Patrimônio: {reais(geral.patrimonio_brl)}")
        print("  Alocação: " + ", ".join(f"{f.grupo} {pct(f.percentual)}" for f in geral.alocacao))
        for inst in (rico, xp):
            resumo = carteira.por_instituicao(inst.id)
            patrimonio = reais(resumo.patrimonio_brl)
            print(f"\nAnálise por Instituição: {inst.nome} -> patrimônio {patrimonio}")
        resumo = obter_resumo_mensal(s, 2025, 3)
        print(
            f"\nMarço/2025: receitas {reais(resumo.total_receitas)}, despesas "
            f"{reais(resumo.total_despesas)}, saldo {reais(resumo.saldo)}"
        )
        serie = serie_patrimonio(s, date(2025, 8, 29), date(2025, 9, 1))
        print("\nSérie de patrimônio (últimos dias):")
        for ponto in serie.pontos:
            print(f"  {ponto.data:%d/%m/%Y}: {reais(ponto.patrimonio)}")
    engine.dispose()


if __name__ == "__main__":
    main()
