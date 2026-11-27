"""Rebalanceamento por metas (``domain/rebalanceamento``): resultados conferidos à mão.

Exemplo base (decisão 6 do Prompt 10, também em ``docs/CALCULOS.md``):
RF 42.000, Ações BR 28.000, Tesouro 15.000, Ações US 9.000, FII 4.000, Cripto 2.000
(T = 100.000); metas 35/25/15/15/7/3; A = 5.000; N = 105.000.
"""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

import pytest

from app.domain.rebalanceamento import (
    AcaoSugerida,
    ClassePlano,
    EntradaPlano,
    ModoPlano,
    Plano,
    PosicaoPlano,
    acao,
    arredondar_pelo_maior_resto,
    aviso_cotacao,
    desvio_pp,
    dividir_completo,
    dividir_so_aportes,
    estimar_venda,
    montar_plano,
)


def D(valor: str | int) -> Decimal:  # noqa: N802 - atalho legível nos testes
    return Decimal(valor)


VALORES_BASE = {
    "renda_fixa": "42000",
    "acao_br": "28000",
    "tesouro_direto": "15000",
    "acao_us": "9000",
    "fundo_listado": "4000",
    "cripto": "2000",
}
METAS_BASE = {
    "renda_fixa": D(35),
    "acao_br": D(25),
    "tesouro_direto": D(15),
    "acao_us": D(15),
    "fundo_listado": D(7),
    "cripto": D(3),
}


def posicao(
    ativo_id: int,
    tipo: str,
    valor: str,
    custo: str | None = None,
    quantidade: str | None = None,
    defasado: bool = False,
    aviso: str | None = None,
) -> PosicaoPlano:
    return PosicaoPlano(
        ativo_id=ativo_id,
        tipo_ativo=tipo,
        valor=D(valor),
        custo=D(custo if custo is not None else valor),
        quantidade=D(quantidade) if quantidade is not None else None,
        defasado=defasado,
        aviso=aviso,
    )


def base(ids_iniciais: int = 1) -> tuple[PosicaoPlano, ...]:
    return tuple(
        posicao(ids_iniciais + i, tipo, valor)
        for i, (tipo, valor) in enumerate(VALORES_BASE.items())
    )


def plano(
    posicoes: tuple[PosicaoPlano, ...],
    metas: Mapping[str, Decimal],
    aporte: str,
    modo: ModoPlano = ModoPlano.APORTES,
    pesos: Mapping[str, Mapping[int, Decimal]] | None = None,
    tolerancia: int = 5,
) -> Plano:
    return montar_plano(
        EntradaPlano(
            posicoes=posicoes,
            metas_classe=metas,
            pesos=pesos or {},
            aporte=D(aporte),
            modo=modo,
            tolerancia_pp=tolerancia,
        )
    )


def por_tipo(resultado: Plano) -> dict[str, ClassePlano]:
    return {c.tipo_ativo: c for c in resultado.classes}


def sugestoes(resultado: Plano) -> dict[str, Decimal | None]:
    return {c.tipo_ativo: c.sugestao for c in resultado.classes}


# ---------------------------------------------------------------- exemplo base


def test_exemplo_base_so_com_aportes() -> None:
    # Déficits (meta × 105.000 − atual): RF 0, Ações BR 0, Tesouro 750, US 6.750, FII 3.350,
    # Cripto 1.150; Σ 12.000 > 5.000 → divisão proporcional: 5.000 × 750 / 12.000 = 312,50;
    # 6.750 → 2.812,50; 3.350 → 1.395,833… → 1.395,83; 1.150 → 479,166… → 479,17.
    resultado = plano(base(), METAS_BASE, "5000")
    assert sugestoes(resultado) == {
        "renda_fixa": D("0.00"),
        "acao_br": D("0.00"),
        "tesouro_direto": D("312.50"),
        "acao_us": D("2812.50"),
        "fundo_listado": D("1395.83"),
        "cripto": D("479.17"),
    }
    assert sum(s or 0 for s in sugestoes(resultado).values()) == D("5000.00")
    assert resultado.total == D(100000)
    # Ordem de apresentação: maior valor atual primeiro.
    assert [c.tipo_ativo for c in resultado.classes] == list(VALORES_BASE)


def test_exemplo_base_completo() -> None:
    # Diferença = meta × 105.000 − atual: RF 36.750 − 42.000 = −5.250; Ações BR 26.250 −
    # 28.000 = −1.750; Tesouro +750; US +6.750; FII +3.350; Cripto +1.150; Σ = 5.000.
    resultado = plano(base(), METAS_BASE, "5000", ModoPlano.COMPLETO)
    assert sugestoes(resultado) == {
        "renda_fixa": D("-5250.00"),
        "acao_br": D("-1750.00"),
        "tesouro_direto": D("750.00"),
        "acao_us": D("6750.00"),
        "fundo_listado": D("3350.00"),
        "cripto": D("1150.00"),
    }
    assert sum(s or 0 for s in sugestoes(resultado).values()) == D("5000.00")


def test_desvios_banda_e_desvio_total_do_exemplo_base() -> None:
    # % atual sobre T = 100.000: 42/28/15/9/4/2. Desvios: +7, +3, 0, −6, −3, −1 p.p.
    # Fora da banda de 5 p.p.: RF (+7) e US (−6). Desvio total = (7+3+0+6+3+1)/2 = 10 p.p.
    resultado = plano(base(), METAS_BASE, "0")
    classes = por_tipo(resultado)
    assert {t: c.desvio_pp for t, c in classes.items()} == {
        "renda_fixa": D("7.00"),
        "acao_br": D("3.00"),
        "tesouro_direto": D("0.00"),
        "acao_us": D("-6.00"),
        "fundo_listado": D("-3.00"),
        "cripto": D("-1.00"),
    }
    assert [t for t, c in classes.items() if c.fora_da_banda] == ["renda_fixa", "acao_us"]
    assert resultado.classes_fora_da_banda == 2
    assert resultado.desvio_total_pp == D("10.00")
    assert classes["renda_fixa"].percentual_atual == D(42)
    # Tolerância 7: RF (|7| não é > 7) fica dentro; nenhuma fora.
    assert plano(base(), METAS_BASE, "0", tolerancia=7).classes_fora_da_banda == 0
    assert plano(base(), METAS_BASE, "0", tolerancia=1).classes_fora_da_banda == 4


# ---------------------------------------------------------------- casos do modo só com aportes


def test_deficits_iguais_ao_aporte_sao_preenchidos_exatamente() -> None:
    # Com metas somando 100%, Σ déficits ≥ A sempre (Σ (meta × N − atual) = N − T = A).
    # O limite é Σ déficits = A, quando nenhuma classe está acima da meta: cada déficit é
    # preenchido e não sobra nada. RF 6.000 (meta 60), Ações 2.000 (meta 40); A = 2.000;
    # N = 10.000; déficits RF 6.000 − 6.000 = 0 e Ações 4.000 − 2.000 = 2.000 (Σ = A).
    resultado = plano(
        (posicao(1, "renda_fixa", "6000"), posicao(2, "acao_br", "2000")),
        {"renda_fixa": D(60), "acao_br": D(40)},
        "2000",
    )
    assert sugestoes(resultado) == {"renda_fixa": D("0.00"), "acao_br": D("2000.00")}


def test_sobra_apos_os_deficits_vai_pelas_metas() -> None:
    # Ramo "Σ déficits < A" da função pura (só alcançável quando as metas não somam 100%,
    # como dentro de uma chamada direta): atuais 100 e 0, metas 50% e 30%, A = 200.
    # N = 300; déficits: 150 − 100 = 50 e 90 − 0 = 90 (Σ 140 < 200); sobra 60 pelas metas:
    # 50 + 60 × 0,5 = 80 e 90 + 60 × 0,3 = 108.
    assert dividir_so_aportes([D(100), D(0)], [D("0.5"), D("0.3")], D(200)) == [D(80), D(108)]


def test_classe_acima_da_meta_nao_recebe_aporte() -> None:
    resultado = plano(base(), METAS_BASE, "1000")
    assert por_tipo(resultado)["renda_fixa"].sugestao == D("0.00")
    assert por_tipo(resultado)["acao_br"].sugestao == D("0.00")
    assert all((c.sugestao or 0) >= 0 for c in resultado.classes)


def test_aporte_zero_nao_sugere_nada_mas_mostra_desvios() -> None:
    resultado = plano(base(), METAS_BASE, "0")
    assert set(sugestoes(resultado).values()) == {D("0.00")}
    assert all(acao(c.sugestao) is AcaoSugerida.MANTER for c in resultado.classes)


def test_aporte_zero_no_modo_completo_so_troca_entre_classes() -> None:
    # N = T = 100.000: RF 35.000 − 42.000 = −7.000; US 15.000 − 9.000 = +6.000; Σ = 0.
    resultado = plano(base(), METAS_BASE, "0", ModoPlano.COMPLETO)
    assert por_tipo(resultado)["renda_fixa"].sugestao == D("-7000.00")
    assert por_tipo(resultado)["acao_us"].sugestao == D("6000.00")
    assert sum(s or 0 for s in sugestoes(resultado).values()) == 0


def test_maior_resto_fecha_os_centavos() -> None:
    # Três classes sem posição com a mesma meta (30%) e uma classe já acima da meta (10%).
    # A = 100; déficits iguais → 33,333… cada; arredondado: 33,33 × 3 = 99,99; o centavo
    # que falta vai para a primeira da ordem (empate; ordem = slug, pois valor e meta empatam).
    resultado = plano(
        (posicao(1, "renda_fixa", "1000"),),
        {"renda_fixa": D(10), "acao_br": D(30), "acao_us": D(30), "cripto": D(30)},
        "100",
    )
    # N = 1.100: RF 110 − 1.000 < 0 → 0; as três outras 330 cada (Σ 990 > 100) → 100/3.
    assert sugestoes(resultado) == {
        "renda_fixa": D("0.00"),
        "acao_br": D("33.34"),
        "acao_us": D("33.33"),
        "cripto": D("33.33"),
    }


def test_arredondar_pelo_maior_resto_direto() -> None:
    terco = D(100) / D(3)
    assert arredondar_pelo_maior_resto([terco, terco, terco], D(100)) == [
        D("33.34"),
        D("33.33"),
        D("33.33"),
    ]
    # 2/3 de 1,00 em duas partes: 0,666… e 0,333… → 0,67 + 0,33 = 1,00 (sem ajuste).
    assert arredondar_pelo_maior_resto([D(2) / D(3), D(1) / D(3)], D(1)) == [D("0.67"), D("0.33")]
    # Falta de centavo: duas partes de 0,005 (meio centavo) e total 0,01. HALF_EVEN dá
    # 0,00 cada (Σ 0) → falta 0,01, vai para a primeira.
    assert arredondar_pelo_maior_resto([D("0.005")] * 2, D("0.01")) == [D("0.01"), D("0.00")]
    # Zero nunca recebe centavo; negativos também fecham.
    assert arredondar_pelo_maior_resto([D(0), -terco, -terco, -terco], D(-100)) == [
        D("0.00"),
        D("-33.34"),
        D("-33.33"),
        D("-33.33"),
    ]
    with pytest.raises(ValueError, match="2 casas"):
        arredondar_pelo_maior_resto([D(1)], D("1.001"))


def test_classe_sem_posicao_e_classe_sem_meta() -> None:
    # Cripto tem meta e nenhuma posição (atual 0%); ETF US tem posição e nenhuma meta
    # (meta 0%, desvio aparece). T = 10.000: RF 8.000 (meta 70), ETF US 2.000 (meta 0),
    # Cripto 0 (meta 30). Desvios: RF 80 − 70 = +10; ETF 20 − 0 = +20; Cripto 0 − 30 = −30.
    resultado = plano(
        (posicao(1, "renda_fixa", "8000"), posicao(2, "etf_us", "2000")),
        {"renda_fixa": D(70), "cripto": D(30)},
        "1000",
    )
    classes = por_tipo(resultado)
    assert classes["cripto"].percentual_atual == 0
    assert classes["cripto"].desvio_pp == D("-30.00")
    assert classes["etf_us"].meta == 0
    assert classes["etf_us"].desvio_pp == D("20.00")
    # N = 11.000: déficits RF 7.700 − 8.000 < 0; ETF 0; Cripto 3.300 (Σ > A) → tudo em Cripto.
    assert sugestoes(resultado) == {
        "renda_fixa": D("0.00"),
        "etf_us": D("0.00"),
        "cripto": D("1000.00"),
    }
    # Completo: ETF sem meta é vendido inteiro (−2.000); RF 7.700 − 8.000 = −300; Cripto
    # +3.300. Σ = 1.000.
    completo = plano(
        (posicao(1, "renda_fixa", "8000"), posicao(2, "etf_us", "2000")),
        {"renda_fixa": D(70), "cripto": D(30)},
        "1000",
        ModoPlano.COMPLETO,
    )
    assert sugestoes(completo) == {
        "renda_fixa": D("-300.00"),
        "etf_us": D("-2000.00"),
        "cripto": D("3300.00"),
    }


def test_carteira_vazia_com_metas() -> None:
    # T = 0: % atual 0 em tudo; o aporte vai inteiro pelas metas (60/40 de 1.000).
    resultado = plano((), {"renda_fixa": D(60), "acao_br": D(40)}, "1000")
    assert sugestoes(resultado) == {"renda_fixa": D("600.00"), "acao_br": D("400.00")}
    assert por_tipo(resultado)["renda_fixa"].desvio_pp == D("-60.00")


def test_sem_metas_so_mostra_o_atual() -> None:
    resultado = plano(base(), {}, "5000")
    assert not resultado.tem_metas
    assert resultado.desvio_total_pp is None
    assert resultado.classes_fora_da_banda == 0
    assert all(c.meta is None and c.sugestao is None for c in resultado.classes)
    assert all(a.sugestao is None for c in resultado.classes for a in c.ativos)
    assert por_tipo(resultado)["renda_fixa"].percentual_atual == D(42)


def test_aporte_invalido_e_recusado() -> None:
    with pytest.raises(ValueError, match="aporte"):
        plano(base(), METAS_BASE, "-1")
    with pytest.raises(ValueError, match="aporte"):
        plano(base(), METAS_BASE, "10.001")


# ---------------------------------------------------------------- pesos por ativo


def _acoes_com_pesos() -> tuple[PosicaoPlano, ...]:
    # Ações BR 28.000 = PETR4 (id 10) 18.000 + VALE3 (id 11) 10.000 + ITUB4 (id 12) 0 (sem
    # posição, só peso). Demais classes do exemplo base.
    outras = tuple(p for p in base() if p.tipo_ativo != "acao_br")
    return (
        *outras,
        posicao(10, "acao_br", "18000", custo="15000", quantidade="600"),
        posicao(11, "acao_br", "10000", custo="12000", quantidade="200"),
    )


PESOS_ACOES = {"acao_br": {10: D(40), 11: D(40), 12: D(20)}}


def test_pesos_dividem_a_sugestao_da_classe_entre_os_ativos() -> None:
    # Metas: Ações BR 30 (no lugar de RF 35 → 30). Metas 30/30/15/15/7/3 somam 100.
    metas = {**METAS_BASE, "renda_fixa": D(30), "acao_br": D(30)}
    resultado = plano(_acoes_com_pesos(), metas, "5000", pesos=PESOS_ACOES)
    acoes = por_tipo(resultado)["acao_br"]
    # Classe: N = 105.000; déficits RF 31.500 − 42.000 < 0; Ações 31.500 − 28.000 = 3.500;
    # Tesouro 750; US 6.750; FII 3.350; Cripto 1.150 → Σ 15.500 > 5.000; Ações recebe
    # 5.000 × 3.500 / 15.500 = 1.129,032… → 1.129,03.
    assert acoes.usa_pesos
    assert acoes.sugestao == D("1129.03")
    # Dentro da classe: N_c = 28.000 + 1.129,03 = 29.129,03; pesos 40/40/20:
    # PETR4 11.651,612 − 18.000 < 0 → 0; VALE3 11.651,612 − 10.000 = 1.651,612;
    # ITUB4 5.825,806 − 0 = 5.825,806; Σ 7.477,418 > 1.129,03 → proporcional:
    # VALE3 1.129,03 × 1.651,612 / 7.477,418 = 249,380… → 249,38; ITUB4 879,649… → 879,65
    ativos = {a.ativo_id: a for a in acoes.ativos}
    assert [a.ativo_id for a in acoes.ativos] == [10, 11, 12]  # maior valor primeiro
    assert ativos[10].sugestao == D("0.00")
    assert ativos[11].sugestao == D("249.38")
    assert ativos[12].sugestao == D("879.65")
    assert sum(a.sugestao or 0 for a in acoes.ativos) == acoes.sugestao
    assert ativos[12].valor_atual == 0
    assert ativos[12].peso == D(20)


def test_pesos_no_modo_completo_com_lucro_estimado() -> None:
    metas = {**METAS_BASE, "renda_fixa": D(30), "acao_br": D(30)}
    resultado = plano(_acoes_com_pesos(), metas, "5000", ModoPlano.COMPLETO, PESOS_ACOES)
    acoes = por_tipo(resultado)["acao_br"]
    # Classe: 0,30 × 105.000 − 28.000 = +3.500. N_c = 31.500: PETR4 12.600 − 18.000 =
    # −5.400; VALE3 12.600 − 10.000 = +2.600; ITUB4 6.300. Σ = 3.500.
    assert acoes.sugestao == D("3500.00")
    ativos = {a.ativo_id: a for a in acoes.ativos}
    assert (ativos[10].sugestao, ativos[11].sugestao, ativos[12].sugestao) == (
        D("-5400.00"),
        D("2600.00"),
        D("6300.00"),
    )
    # Venda de PETR4: preço 18.000/600 = 30; PM 15.000/600 = 25. Quantidade 5.400/30 = 180;
    # lucro 5.400 − 180 × 25 = 900.
    assert ativos[10].quantidade_estimada == D(180)
    assert ativos[10].lucro_estimado == D(900)
    assert ativos[11].lucro_estimado is None
    assert ativos[11].quantidade_estimada is None


def test_classe_com_aporte_zero_nao_divide_entre_ativos() -> None:
    resultado = plano(_acoes_com_pesos(), METAS_BASE, "5000", pesos=PESOS_ACOES)
    acoes = por_tipo(resultado)["acao_br"]  # Ações BR acima da meta: recebe 0
    assert acoes.sugestao == D("0.00")
    assert all(a.sugestao == D("0.00") for a in acoes.ativos)


def test_pesos_que_nao_somam_100_sao_ignorados_com_aviso() -> None:
    pesos = {"acao_br": {10: D(40), 11: D(40)}}  # ITUB4 excluído: sobrou 80%
    resultado = plano(_acoes_com_pesos(), METAS_BASE, "5000", pesos=pesos)
    acoes = por_tipo(resultado)["acao_br"]
    assert not acoes.usa_pesos
    assert resultado.classes_com_pesos_invalidos == ("acao_br",)
    assert all(a.sugestao is None and a.peso is None for a in acoes.ativos)
    assert {a.ativo_id for a in acoes.ativos} == {10, 11}  # só as posições


def test_classe_sem_pesos_lista_as_posicoes_sem_sugestao() -> None:
    resultado = plano(_acoes_com_pesos(), METAS_BASE, "5000", ModoPlano.COMPLETO)
    acoes = por_tipo(resultado)["acao_br"]
    assert acoes.sugestao == D("-1750.00")
    assert not acoes.usa_pesos
    assert all(a.sugestao is None and a.lucro_estimado is None for a in acoes.ativos)


# ---------------------------------------------------------------- venda, avisos e ação


def test_estimar_venda() -> None:
    # 100 cotas, valor 5.000 (preço 50), custo 4.000 (PM 40); vender 1.000 → 20 cotas,
    # lucro 1.000 − 20 × 40 = 200.
    assert estimar_venda(D(1000), D(5000), D(4000), D(100)) == (D(20), D(200))
    # Prejuízo: custo 6.000 (PM 60) → 1.000 − 20 × 60 = −200.
    assert estimar_venda(D(1000), D(5000), D(6000), D(100)) == (D(20), D(-200))
    # Renda fixa (sem quantidade): lucro pela proporção 1.000 × (5.000 − 4.000)/5.000 = 200.
    assert estimar_venda(D(1000), D(5000), D(4000), None) == (None, D(200))
    assert estimar_venda(D(0), D(5000), D(4000), D(100)) == (None, None)
    assert estimar_venda(D(10), D(0), D(0), D(1)) == (None, None)


def test_ativo_defasado_leva_aviso_para_a_linha() -> None:
    hoje = date(2026, 11, 26)
    assert (
        aviso_cotacao(
            defasado=True, erro=None, aviso=None, data_preco=date(2026, 11, 23), hoje=hoje
        )
        == "Cotação de 3 dias atrás."
    )
    assert (
        aviso_cotacao(
            defasado=True, erro=None, aviso=None, data_preco=date(2026, 11, 25), hoje=hoje
        )
        == "Cotação de 1 dia atrás."
    )
    assert (
        aviso_cotacao(defasado=True, erro=None, aviso="Câmbio antigo.", data_preco=None, hoje=hoje)
        == "Câmbio antigo."
    )
    assert aviso_cotacao(defasado=False, erro=None, aviso=None, data_preco=hoje, hoje=hoje) is None
    assert aviso_cotacao(
        defasado=False, erro="Câmbio ausente.", aviso=None, data_preco=None, hoje=hoje
    ) == ("Sem valor atual (ficou fora do cálculo): Câmbio ausente.")
    # O aviso chega até a sugestão do ativo.
    posicoes = (
        posicao(1, "renda_fixa", "5000"),
        posicao(
            2, "acao_br", "5000", quantidade="10", defasado=True, aviso="Cotação de 3 dias atrás."
        ),
    )
    resultado = plano(posicoes, {"renda_fixa": D(50), "acao_br": D(50)}, "0")
    item = por_tipo(resultado)["acao_br"].ativos[0]
    assert item.defasado
    assert item.aviso == "Cotação de 3 dias atrás."


def test_acao_e_desvio() -> None:
    assert acao(D("0.01")) is AcaoSugerida.APORTAR
    assert acao(D("-0.01")) is AcaoSugerida.VENDER
    assert acao(D("0.00")) is AcaoSugerida.MANTER
    assert acao(D("0.004")) is AcaoSugerida.MANTER
    assert acao(None) is AcaoSugerida.MANTER
    assert desvio_pp(D("28.004"), D(25)) == D("3.00")
    assert dividir_completo([D(10), D(0)], [D("0.5"), D("0.5")], D(10)) == [D(0), D(10)]
