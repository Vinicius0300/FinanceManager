"""Ponto único de registro dos tipos de ativo.

Para adicionar um tipo, crie o handler em um arquivo próprio e acrescente-o a
``HANDLERS_PADRAO``. Nenhum outro handler precisa ser alterado.
"""

from app.asset_types.acao_br import AcaoBr
from app.asset_types.acao_us import AcaoUs
from app.asset_types.base import HandlerTipoAtivo
from app.asset_types.cripto import Cripto
from app.asset_types.fundo import Fundo
from app.asset_types.poupanca import Poupanca
from app.asset_types.registry import RegistroTiposAtivo
from app.asset_types.renda_fixa import RendaFixa
from app.asset_types.tesouro_direto import TesouroDireto

HANDLERS_PADRAO: tuple[type[HandlerTipoAtivo], ...] = (
    AcaoBr,
    AcaoUs,
    Fundo,
    RendaFixa,
    Cripto,
    Poupanca,
    TesouroDireto,
)


def criar_registro_padrao() -> RegistroTiposAtivo:
    registro = RegistroTiposAtivo()
    for classe in HANDLERS_PADRAO:
        registro.registrar(classe())
    return registro


REGISTRO_PADRAO = criar_registro_padrao()
