"""Ações, units e BDRs negociados na B3 (BRL).

ETFs e fundos listados (FII, Fiagro, FI-Infra) têm tipos próprios (``etf_br`` e
``fundo_listado``), identificados pela categoria oficial do cadastro da B3.
"""

from typing import ClassVar

from app.asset_types.base import CampoEspecifico, HandlerCotado, Opcao, TipoCampo
from app.domain.agenda import AGENDA_B3, Agenda


class AcaoBr(HandlerCotado):
    slug = "acao_br"
    nome = "Ação (Brasil)"
    descricao = "Ações, units e BDRs negociados na B3."
    moedas_aceitas = ("BRL",)
    agenda: ClassVar[Agenda] = AGENDA_B3
    provider = "yfinance"
    lista_simbolos: ClassVar[str | None] = "B3"
    sufixo_simbolo_externo: ClassVar[str] = ".SA"
    campos = (
        CampoEspecifico(
            nome="tipo_papel",
            rotulo="Tipo de papel",
            tipo=TipoCampo.ESCOLHA,
            obrigatorio=False,
            opcoes=(
                Opcao("ON", "Ordinária (ON)"),
                Opcao("PN", "Preferencial (PN)"),
                Opcao("UNIT", "Unit"),
                Opcao("BDR", "BDR"),
            ),
        ),
        CampoEspecifico(
            nome="setor",
            rotulo="Setor",
            tipo=TipoCampo.TEXTO,
            obrigatorio=False,
            tamanho_maximo=60,
        ),
    )
