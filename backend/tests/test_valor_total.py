"""Compra e venda informadas pelo valor total (Tesouro Direto): preço calculado no backend."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.asset_types.base import Identidade
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.domain.conta_corrente import preco_pelo_valor_total
from app.domain.enums import TipoTransacao
from app.domain.erros import ValidacaoError
from app.repositories import modelos as m
from app.services import caixa
from app.services.cadastros import NovoAtivo, criar_ativo
from app.services.transacoes import NovaTransacao, editar_transacao, registrar_transacao
from tests.fabricas import D, acao_br, deposito, instituicao

DIA = date(2026, 3, 2)


def tesouro(sessao: Session) -> m.Ativo:
    return criar_ativo(
        sessao,
        NovoAtivo(
            tipo="tesouro_direto",
            nome="Tesouro IPCA+ 2035",
            metadados={"titulo": "ipca", "vencimento": "2035-05-15"},
        ),
    )


def operacao(ativo: m.Ativo, inst: m.Instituicao, **campos: object) -> NovaTransacao:
    padrao: dict[str, object] = {
        "ativo_id": ativo.id,
        "instituicao_id": inst.id,
        "tipo": TipoTransacao.COMPRA,
        "data": DIA,
        "quantidade": D("0.07"),
        "valor_total": D("1066.42"),
    }
    return NovaTransacao(**{**padrao, **campos})  # type: ignore[arg-type]


@pytest.fixture
def rico(sessao: Session) -> m.Instituicao:
    inst = instituicao(sessao)
    deposito(sessao, inst, "5000", date(2026, 1, 2))
    return inst


def test_preco_e_o_valor_dividido_pela_quantidade_em_8_casas() -> None:
    # 1.066,42 ÷ 0,07 = 15.234,571428571... → 15.234,57142857
    # 0,07 × 15.234,57142857 = 1.066,4199999999 → R$ 1.066,42 no caixa
    assert preco_pelo_valor_total(D("1066.42"), D("0.07")) == D("15234.57142857")
    # Divisão exata: 1.000 ÷ 0,5 = 2.000
    assert preco_pelo_valor_total(D("1000"), D("0.5")) == D("2000")


@pytest.mark.parametrize(
    ("valor", "quantidade", "campo"),
    [
        (Decimal("0"), Decimal("1"), "valor_total"),
        (Decimal("10"), Decimal("0"), "quantidade"),
        # 0,01 ÷ 10.000.000.000 = 0,000000000001 → preço 0: o caixa não daria R$ 0,01.
        (Decimal("0.01"), Decimal("10000000000"), "valor_total"),
        # Resultado com dígitos demais para caber com 8 casas.
        (Decimal("9999999999999999999999"), Decimal("0.00000001"), "valor_total"),
    ],
)
def test_recusa_combinacoes_inviaveis(valor: Decimal, quantidade: Decimal, campo: str) -> None:
    with pytest.raises(ValidacaoError) as erro:
        preco_pelo_valor_total(valor, quantidade)
    assert erro.value.detalhes[0].campo == campo


def test_compra_pelo_valor_investido_debita_exatamente_o_valor(
    sessao: Session, rico: m.Instituicao
) -> None:
    resultado = registrar_transacao(sessao, operacao(tesouro(sessao), rico))
    assert resultado.transacao is not None
    assert resultado.transacao.quantidade == D("0.07")  # igual ao extrato
    assert resultado.transacao.preco_unitario == D("15234.57142857")
    # 5.000 − 1.066,42 = 3.933,58
    assert caixa.saldo(sessao, rico.id, "BRL", DIA) == D("3933.58")


def test_venda_pelo_valor_recebido_credita_exatamente_o_valor(
    sessao: Session, rico: m.Instituicao
) -> None:
    ativo = tesouro(sessao)
    registrar_transacao(sessao, operacao(ativo, rico))
    registrar_transacao(
        sessao,
        operacao(
            ativo,
            rico,
            tipo=TipoTransacao.VENDA,
            data=date(2026, 3, 3),
            valor_total=D("1100.00"),
        ),
    )
    # 3.933,58 + 1.100,00 = 5.033,58
    assert caixa.saldo(sessao, rico.id, "BRL", date(2026, 3, 3)) == D("5033.58")


def test_edicao_pelo_valor_total_refaz_preco_e_caixa(sessao: Session, rico: m.Instituicao) -> None:
    ativo = tesouro(sessao)
    original = registrar_transacao(sessao, operacao(ativo, rico)).transacao
    assert original is not None
    editada = editar_transacao(
        sessao, original.id, operacao(ativo, rico, valor_total=D("1400.00"))
    ).transacao
    assert editada is not None
    assert editada.preco_unitario == D("20000")  # 1.400 ÷ 0,07
    assert caixa.saldo(sessao, rico.id, "BRL", DIA) == D("3600.00")


def test_preco_e_valor_total_juntos_sao_recusados(sessao: Session, rico: m.Instituicao) -> None:
    dados = operacao(tesouro(sessao), rico, preco_unitario=D("15234.56"))
    with pytest.raises(ValidacaoError, match="não os dois"):
        registrar_transacao(sessao, dados)


def test_valor_total_com_mais_de_2_casas_e_recusado(sessao: Session, rico: m.Instituicao) -> None:
    dados = operacao(tesouro(sessao), rico, valor_total=D("1066.421"))
    with pytest.raises(ValidacaoError, match="casas decimais"):
        registrar_transacao(sessao, dados)


def test_tipo_sem_a_opcao_recusa_valor_total(sessao: Session, rico: m.Instituicao) -> None:
    with pytest.raises(ValidacaoError, match="não aceita informar o valor total"):
        registrar_transacao(sessao, operacao(acao_br(sessao), rico))


def test_tesouro_ignora_simbolo_externo_ao_comparar_titulos() -> None:
    # A fonte usa título + vencimento: um símbolo antigo não separa o mesmo título.
    handler = REGISTRO_PADRAO.obter("tesouro_direto")
    metadados = {"titulo": "ipca", "vencimento": "2035-05-15"}
    assert handler.mesma_identidade(
        Identidade(None, "qualquer", metadados), Identidade(None, None, metadados)
    )
