"""Situação da cotação de um ativo, usada no chip e no painel de status da barra superior.

Cada ativo cai numa única situação, nesta ordem de prioridade:

1. ``com_erro``: a última tentativa de coleta falhou (``ultimo_erro`` preenchido);
2. ``manual``: ativo cotado **sem fonte automática** (sem provider). O app nunca busca o
   preço sozinho, então a idade do preço é mostrada, mas não conta como defasado, e os
   botões de atualizar não o incluem;
3. ``defasado``: preço (ou indicador do cálculo) mais antigo que a tolerância do tipo;
4. ``em_dia``: o resto.

Função pura: não acessa banco nem rede.
"""

from enum import StrEnum


class SituacaoCotacao(StrEnum):
    EM_DIA = "em_dia"
    DEFASADO = "defasado"
    COM_ERRO = "com_erro"
    MANUAL = "manual"


def classificar_situacao(
    *, ultimo_erro: str | None, sem_fonte_automatica: bool, defasado: bool
) -> SituacaoCotacao:
    if ultimo_erro:
        return SituacaoCotacao.COM_ERRO
    if sem_fonte_automatica:
        return SituacaoCotacao.MANUAL
    if defasado:
        return SituacaoCotacao.DEFASADO
    return SituacaoCotacao.EM_DIA
