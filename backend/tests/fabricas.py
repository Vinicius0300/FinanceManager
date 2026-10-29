"""Fábricas de dados sintéticos para os testes de services (sem rede, sem relógio real)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.enums import (
    OrigemPreco,
    SubtipoProvento,
    TipoIndicador,
    TipoInstituicao,
    TipoMovimento,
    TipoTransacao,
)
from app.repositories import modelos as m
from app.services.cadastros import NovoAtivo, criar_ativo, criar_instituicao
from app.services.caixa import NovoMovimentoManual, registrar_movimento_manual
from app.services.mercado import registrar_indicador, registrar_preco
from app.services.transacoes import NovaTransacao, ResultadoTransacao, registrar_transacao


def D(valor: str | int) -> Decimal:  # noqa: N802 - atalho legível nos testes
    return Decimal(valor)


def instituicao(
    sessao: Session, nome: str = "RICO", tipo: TipoInstituicao = TipoInstituicao.CORRETORA
) -> m.Instituicao:
    return criar_instituicao(sessao, nome, tipo)


def acao_br(sessao: Session, simbolo: str = "TST11") -> m.Ativo:
    return criar_ativo(sessao, NovoAtivo(tipo="acao_br", nome=f"Teste {simbolo}", simbolo=simbolo))


def acao_us(sessao: Session, simbolo: str = "AAPL") -> m.Ativo:
    return criar_ativo(sessao, NovoAtivo(tipo="acao_us", nome=f"Teste {simbolo}", simbolo=simbolo))


def cdb(
    sessao: Session,
    indexador: str = "cdi",
    taxa: str = "100",
    aplicacao: date = date(2025, 8, 1),
    vencimento: date = date(2030, 1, 2),
    nome: str = "CDB Banco X",
) -> m.Ativo:
    return criar_ativo(
        sessao,
        NovoAtivo(
            tipo="renda_fixa",
            nome=nome,
            metadados={
                "indexador": indexador,
                "taxa": taxa,
                "data_aplicacao": aplicacao.isoformat(),
                "vencimento": vencimento.isoformat(),
                "emissor": "Banco X",
                "liquidez": "diaria",
            },
        ),
    )


def poupanca(sessao: Session) -> m.Ativo:
    return criar_ativo(sessao, NovoAtivo(tipo="poupanca", nome="Poupança Banco X"))


def deposito(
    sessao: Session, inst: m.Instituicao, valor: str, dia: date, moeda: str = "BRL"
) -> m.MovimentoConta:
    return registrar_movimento_manual(
        sessao, NovoMovimentoManual(inst.id, moeda, TipoMovimento.DEPOSITO, dia, D(valor))
    )


def saque(
    sessao: Session, inst: m.Instituicao, valor: str, dia: date, moeda: str = "BRL"
) -> m.MovimentoConta:
    return registrar_movimento_manual(
        sessao, NovoMovimentoManual(inst.id, moeda, TipoMovimento.SAQUE, dia, D(valor))
    )


def compra(
    sessao: Session,
    ativo: m.Ativo,
    inst: m.Instituicao,
    dia: date,
    quantidade: str,
    preco: str,
    taxas: str = "0",
    cambio: str | None = None,
    aceitar_ajuste: bool = True,
) -> ResultadoTransacao:
    return registrar_transacao(
        sessao,
        NovaTransacao(
            ativo_id=ativo.id,
            instituicao_id=inst.id,
            tipo=TipoTransacao.COMPRA,
            data=dia,
            quantidade=D(quantidade),
            preco_unitario=D(preco),
            taxas=D(taxas),
            cambio=D(cambio) if cambio else None,
        ),
        aceitar_ajuste=aceitar_ajuste,
    )


def venda(
    sessao: Session,
    ativo: m.Ativo,
    inst: m.Instituicao,
    dia: date,
    quantidade: str,
    preco: str,
    taxas: str = "0",
    cambio: str | None = None,
) -> ResultadoTransacao:
    return registrar_transacao(
        sessao,
        NovaTransacao(
            ativo_id=ativo.id,
            instituicao_id=inst.id,
            tipo=TipoTransacao.VENDA,
            data=dia,
            quantidade=D(quantidade),
            preco_unitario=D(preco),
            taxas=D(taxas),
            cambio=D(cambio) if cambio else None,
        ),
    )


def provento(
    sessao: Session,
    ativo: m.Ativo,
    inst: m.Instituicao,
    dia: date,
    valor: str,
    imposto: str = "0",
    subtipo: SubtipoProvento = SubtipoProvento.DIVIDENDO,
    cambio: str | None = None,
) -> ResultadoTransacao:
    return registrar_transacao(
        sessao,
        NovaTransacao(
            ativo_id=ativo.id,
            instituicao_id=inst.id,
            tipo=TipoTransacao.PROVENTO,
            data=dia,
            valor=D(valor),
            subtipo_provento=subtipo,
            imposto_retido=D(imposto),
            cambio=D(cambio) if cambio else None,
        ),
    )


def montante(
    sessao: Session,
    ativo: m.Ativo,
    inst: m.Instituicao,
    tipo: TipoTransacao,
    dia: date,
    valor: str,
    aceitar_ajuste: bool = True,
) -> ResultadoTransacao:
    return registrar_transacao(
        sessao,
        NovaTransacao(
            ativo_id=ativo.id, instituicao_id=inst.id, tipo=tipo, data=dia, valor=D(valor)
        ),
        aceitar_ajuste=aceitar_ajuste,
    )


def preco(sessao: Session, ativo: m.Ativo, dia: date, valor: str) -> m.Preco:
    """Preço manual às 15h UTC (12h em Brasília) do dia informado."""
    return registrar_preco(
        sessao,
        ativo.id,
        datetime(dia.year, dia.month, dia.day, 15, tzinfo=UTC),
        D(valor),
        OrigemPreco.MANUAL,
    )


def indicador(
    sessao: Session, tipo: TipoIndicador, dia: date, valor: str, moeda: str = "BRL"
) -> m.Indicador:
    return registrar_indicador(sessao, tipo, dia, D(valor), moeda)
