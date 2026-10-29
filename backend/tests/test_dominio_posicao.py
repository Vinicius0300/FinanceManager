"""Posição em cotas: preço médio ponderado, taxas, venda parcial, proventos, eventos, câmbio."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import TipoEvento
from app.domain.erros import PosicaoInsuficienteError, ValidacaoError
from app.domain.numeros import ZERO, arredondar_moeda, dividir
from app.domain.posicao import (
    Compra,
    EstadoPosicao,
    EventoCorporativo,
    Provento,
    ValoresPosicao,
    Venda,
    aplicar_operacoes,
    historico_posicao,
    validar_proporcao_evento,
)

D = Decimal
D1, D2, D3, D4, D5 = (date(2025, 1, d) for d in (2, 3, 6, 7, 8))


def test_preco_medio_ponderado() -> None:
    # 10 @ 20 + 10 @ 30 → custo 500, PM = 500 / 20 = 25.
    estado = aplicar_operacoes([Compra(D1, D(10), D(20)), Compra(D2, D(10), D(30))])
    assert estado.quantidade == D(20)
    assert estado.moeda.custo == D(500)
    assert estado.preco_medio == D(25)
    assert estado.moeda.total_investido == D(500)


def test_taxas_de_compra_sobem_pm_e_de_venda_reduzem_lucro() -> None:
    # Compra 100 @ 10 + taxa 5 → custo 1.005, PM 10,05.
    # Venda 100 @ 12 com taxa 4 → lucro = 1.200 − 4 − 1.005 = 191.
    estado = aplicar_operacoes([Compra(D1, D(100), D(10), taxas=D(5))])
    assert estado.preco_medio == D("10.05")
    estado = aplicar_operacoes([Venda(D2, D(100), D(12), taxas=D(4))], estado)
    assert estado.moeda.lucro_realizado == D(191)
    assert estado.zerada
    assert estado.moeda.custo == ZERO
    assert estado.preco_medio is None


def test_venda_parcial_mantem_pm_e_realiza_lucro() -> None:
    # 10 @ 20 + 10 @ 30 → PM 25; vende 5 @ 40 → lucro = (40 − 25) × 5 = 75.
    estado = aplicar_operacoes(
        [Compra(D1, D(10), D(20)), Compra(D2, D(10), D(30)), Venda(D3, D(5), D(40))]
    )
    assert estado.quantidade == D(15)
    assert estado.preco_medio == D(25)
    assert estado.moeda.custo == D(375)
    assert estado.moeda.lucro_realizado == D(75)


def test_venda_com_prejuizo() -> None:
    # 10 @ 50; vende 4 @ 40 → lucro = (40 − 50) × 4 = −40.
    estado = aplicar_operacoes([Compra(D1, D(10), D(50)), Venda(D2, D(4), D(40))])
    assert estado.moeda.lucro_realizado == D(-40)


def test_venda_maior_que_a_posicao_e_erro_de_dominio() -> None:
    with pytest.raises(PosicaoInsuficienteError) as erro:
        aplicar_operacoes([Compra(D1, D(10), D(10)), Venda(D3, D("10.5"), D(10))])
    assert erro.value.mensagem == (
        "Venda de 10,5 maior que a posição disponível de 10 em 06/01/2025."
    )
    assert erro.value.codigo == "posicao_insuficiente"


def test_venda_sem_posicao() -> None:
    with pytest.raises(PosicaoInsuficienteError):
        aplicar_operacoes([Venda(D1, D(1), D(10))])


@pytest.mark.parametrize(
    ("fabrica", "campo"),
    [
        (lambda: Compra(D1, ZERO, D(10)), "quantidade"),
        (lambda: Compra(D1, D(-1), D(10)), "quantidade"),
        (lambda: Compra(D1, D(1), D(-10)), "preco_unitario"),
        (lambda: Compra(D1, D(1), D(10), taxas=D(-1)), "taxas"),
        (lambda: Compra(D1, D(1), D(10), cambio=ZERO), "cambio"),
        (lambda: Venda(D1, ZERO, D(10)), "quantidade"),
        (lambda: Venda(D1, D(1), D(10), taxas=D(11)), "taxas"),
        (lambda: Provento(D1, ZERO), "valor"),
        (lambda: Provento(D1, D(1), imposto_retido=D(-1)), "imposto_retido"),
        (lambda: Provento(D1, D(1), cambio=ZERO), "cambio"),
    ],
)
def test_validacoes_das_operacoes(fabrica: object, campo: str) -> None:
    with pytest.raises(ValidacaoError) as erro:
        fabrica()  # type: ignore[operator]
    assert erro.value.detalhes[0].campo == campo


def test_preco_zero_e_permitido() -> None:
    # Ex.: ações recebidas sem custo. Custo 0 → PM 0.
    assert aplicar_operacoes([Compra(D1, D(10), ZERO)]).preco_medio == ZERO


def test_posicao_zerada_e_reaberta_recomeca_o_pm() -> None:
    # 10 @ 10, vende 10 @ 12 (lucro 20). Reabre com 5 @ 20 → PM 20 (sem herdar o antigo).
    estado = aplicar_operacoes(
        [Compra(D1, D(10), D(10)), Venda(D2, D(10), D(12)), Compra(D3, D(5), D(20))]
    )
    assert estado.preco_medio == D(20)
    assert estado.moeda.lucro_realizado == D(20)
    assert estado.moeda.total_investido == D(200)


def test_vendas_sucessivas_nao_deixam_residuo_de_arredondamento() -> None:
    # Compra 3 @ 1 + taxa 0,01 → custo 3,01 e PM = 1,00333... (dízima).
    # Vende 1 @ 2 e depois 2 @ 2: a última venda leva exatamente o custo restante,
    # então o custo final é 0 e o lucro total é 6 − 3,01 = 2,99 exatos.
    estado = aplicar_operacoes(
        [
            Compra(D1, D(3), D(1), taxas=D("0.01")),
            Venda(D2, D(1), D(2)),
            Venda(D3, D(2), D(2)),
        ]
    )
    assert estado.moeda.custo == ZERO
    assert estado.moeda.lucro_realizado == D("2.99")


def test_proventos_nao_alteram_pm_nem_custo() -> None:
    # Dividendo de 50 e JCP de 85 líquidos (15 retidos) sobre 100 @ 10.
    estado = aplicar_operacoes(
        [
            Compra(D1, D(100), D(10)),
            Provento(D2, D(50)),
            Provento(D3, D(85), imposto_retido=D(15)),
        ]
    )
    assert estado.preco_medio == D(10)
    assert estado.moeda.custo == D(1000)
    assert estado.moeda.proventos == D(135)
    assert estado.moeda.impostos_retidos == D(15)


def test_desdobramento_um_para_dois() -> None:
    # 100 @ 10 → desdobramento 1:2 → 200 ações, custo 1.000, PM 5.
    estado = aplicar_operacoes(
        [Compra(D1, D(100), D(10)), EventoCorporativo(D2, TipoEvento.DESDOBRAMENTO, 1, 2)]
    )
    assert estado.quantidade == D(200)
    assert estado.moeda.custo == D(1000)
    assert estado.preco_medio == D(5)


def test_grupamento_dez_para_um_inclusive_com_fracao() -> None:
    # 100 @ 10 → 10:1 → 10 ações, PM 100. Com 105 ações sobram 10,5 (a fração é
    # vendida em leilão e deve ser registrada pelo usuário como venda).
    estado = aplicar_operacoes(
        [Compra(D1, D(100), D(10)), EventoCorporativo(D2, TipoEvento.GRUPAMENTO, 10, 1)]
    )
    assert estado.quantidade == D(10)
    assert estado.preco_medio == D(100)
    fracionado = aplicar_operacoes(
        [Compra(D1, D(105), D(10)), EventoCorporativo(D2, TipoEvento.GRUPAMENTO, 10, 1)]
    )
    assert fracionado.quantidade == D("10.5")
    assert fracionado.preco_medio == D(100)


def test_bonificacao_com_custo_atribuido() -> None:
    # 100 @ 10 (custo 1.000); bonificação 10% (10:11) com custo atribuído R$ 4:
    # novas = 100 × 1/10 = 10; custo = 1.000 + 10 × 4 = 1.040; PM = 1.040 / 110 = 9,4545...
    # Venda das 110 @ 12 → lucro = 1.320 − 1.040 = 280.
    estado = aplicar_operacoes(
        [
            Compra(D1, D(100), D(10)),
            EventoCorporativo(D2, TipoEvento.BONIFICACAO, 10, 11, custo_unitario=D(4)),
        ]
    )
    assert estado.quantidade == D(110)
    assert estado.moeda.custo == D(1040)
    assert estado.preco_medio == dividir(D(1040), D(110))
    assert arredondar_moeda(estado.preco_medio) == D("9.45")
    assert estado.moeda.rendimentos_bonificacao == D(40)
    assert estado.moeda.total_investido == D(1000)  # bonificação não é dinheiro novo
    vendido = aplicar_operacoes([Venda(D3, D(110), D(12))], estado)
    assert vendido.moeda.lucro_realizado == D(280)


def test_bonificacao_sem_custo_dilui_o_pm() -> None:
    # 100 @ 10 + 10:11 sem custo → 110 ações, custo 1.000, PM 9,0909...
    estado = aplicar_operacoes(
        [Compra(D1, D(100), D(10)), EventoCorporativo(D2, TipoEvento.BONIFICACAO, 10, 11)]
    )
    assert estado.moeda.custo == D(1000)
    assert arredondar_moeda(estado.preco_medio or ZERO) == D("9.09")


def test_evento_sobre_posicao_zerada_nao_faz_nada() -> None:
    estado = aplicar_operacoes([EventoCorporativo(D1, TipoEvento.DESDOBRAMENTO, 1, 2)])
    assert estado == EstadoPosicao()


def test_evento_vem_antes_das_transacoes_do_mesmo_dia() -> None:
    # A data do evento é a data "ex": a compra do mesmo dia já é feita com a ação ajustada.
    # 100 @ 10; no dia 2: desdobramento 1:2 e compra de 10 @ 5 → 100 × 2 + 10 = 210.
    estado = aplicar_operacoes(
        [
            Compra(D1, D(100), D(10), ordem=1),
            Compra(D2, D(10), D(5), ordem=2),
            EventoCorporativo(D2, TipoEvento.DESDOBRAMENTO, 1, 2, ordem=99),
        ]
    )
    assert estado.quantidade == D(210)
    assert estado.moeda.custo == D(1050)


def test_transacoes_do_mesmo_dia_seguem_a_ordem_de_registro() -> None:
    compra = Compra(D1, D(10), D(10), ordem=2)
    with pytest.raises(PosicaoInsuficienteError):
        aplicar_operacoes([compra, Venda(D1, D(5), D(10), ordem=1)])
    estado = aplicar_operacoes([compra, Venda(D1, D(5), D(10), ordem=3)])
    assert estado.quantidade == D(5)


def test_multimoeda_custo_em_brl_fixo_no_cambio_de_cada_compra() -> None:
    # Compra 10 @ US$ 100 + US$ 1 de taxa, câmbio 5,00 → custo US$ 1.001 = R$ 5.005.
    # Compra 10 @ US$ 110, câmbio 5,50 → +US$ 1.100 = +R$ 6.050.
    # Total: US$ 2.101 / R$ 11.055; PM US$ 105,05 / R$ 552,75.
    # Venda 5 @ US$ 120, câmbio 6,00:
    #   custo que sai = US$ 2.101 × 5/20 = 525,25 e R$ 11.055 × 5/20 = 2.763,75;
    #   lucro US$ = 600 − 525,25 = 74,75; lucro R$ = 600 × 6 − 2.763,75 = 836,25.
    estado = aplicar_operacoes(
        [
            Compra(D1, D(10), D(100), taxas=D(1), cambio=D("5.00")),
            Compra(D2, D(10), D(110), cambio=D("5.50")),
        ]
    )
    assert estado.moeda.custo == D(2101)
    assert estado.brl.custo == D(11055)
    assert estado.preco_medio == D("105.05")
    assert estado.preco_medio_brl == D("552.75")
    estado = aplicar_operacoes([Venda(D3, D(5), D(120), cambio=D("6.00"))], estado)
    assert estado.moeda.lucro_realizado == D("74.75")
    assert estado.brl.lucro_realizado == D("836.25")
    assert estado.brl.custo == D("8291.25")


def test_provento_e_bonificacao_em_moeda_estrangeira() -> None:
    # Provento líquido US$ 10 (US$ 4,29 retidos, 30%), câmbio 5 → R$ 50 e R$ 21,45.
    # Bonificação 10:11 com custo US$ 4 e câmbio 5 → custo +US$ 40 = +R$ 200.
    estado = aplicar_operacoes(
        [
            Compra(D1, D(100), D(10), cambio=D(5)),
            Provento(D2, D(10), imposto_retido=D("4.29"), cambio=D(5)),
            EventoCorporativo(D3, TipoEvento.BONIFICACAO, 10, 11, custo_unitario=D(4), cambio=D(5)),
        ]
    )
    assert estado.brl.proventos == D(50)
    assert estado.brl.impostos_retidos == D("21.45")
    assert estado.moeda.custo == D(1040)
    assert estado.brl.custo == D(5200)
    assert estado.brl.rendimentos_bonificacao == D(200)


def test_historico_guarda_o_estado_ao_fim_de_cada_dia() -> None:
    historico = historico_posicao(
        [
            Compra(D1, D(10), D(10), ordem=1),
            Compra(D1, D(10), D(20), ordem=2),
            Venda(D3, D(5), D(30), ordem=3),
        ]
    )
    assert [dia for dia, _ in historico] == [D1, D3]
    assert historico[0][1].quantidade == D(20)
    assert historico[1][1].quantidade == D(15)


def test_soma_de_valores_posicao() -> None:
    a = ValoresPosicao(D(1), D(2), D(3), D(4), D(5), D(6))
    assert a + a == ValoresPosicao(D(2), D(4), D(6), D(8), D(10), D(12))


@pytest.mark.parametrize(
    ("tipo", "de", "para", "custo", "campo"),
    [
        (TipoEvento.GRUPAMENTO, 1, 10, ZERO, "proporcao"),
        (TipoEvento.DESDOBRAMENTO, 2, 1, ZERO, "proporcao"),
        (TipoEvento.BONIFICACAO, 11, 10, ZERO, "proporcao"),
        (TipoEvento.DESDOBRAMENTO, 0, 2, ZERO, "proporcao"),
        (TipoEvento.DESDOBRAMENTO, 1, 2, D(1), "custo_unitario"),
        (TipoEvento.BONIFICACAO, 10, 11, D(-1), "custo_unitario"),
    ],
)
def test_validacao_de_proporcao_dos_eventos(
    tipo: TipoEvento, de: int, para: int, custo: Decimal, campo: str
) -> None:
    with pytest.raises(ValidacaoError) as erro:
        validar_proporcao_evento(tipo, de, para, custo)
    assert erro.value.detalhes[0].campo == campo
    with pytest.raises(ValidacaoError):
        EventoCorporativo(D1, tipo, de, para, custo)


def test_evento_com_cambio_invalido() -> None:
    with pytest.raises(ValidacaoError):
        EventoCorporativo(D1, TipoEvento.DESDOBRAMENTO, 1, 2, cambio=ZERO)
