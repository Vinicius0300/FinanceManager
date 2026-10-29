"""Fundos de investimento (cotas; valor da cota pela CVM)."""

import re
from typing import ClassVar

from app.asset_types.base import CampoEspecifico, HandlerCotado, Metadados, Opcao, TipoCampo
from app.domain.erros import DetalheCampo

_SO_DIGITOS = re.compile(r"\D")


def cnpj_valido(cnpj: str) -> bool:
    """Valida os dígitos verificadores de um CNPJ (com ou sem pontuação)."""
    digitos = _SO_DIGITOS.sub("", cnpj)
    if len(digitos) != 14 or digitos == digitos[0] * 14:
        return False
    numeros = [int(d) for d in digitos]
    for posicao in (12, 13):
        pesos = list(range(posicao - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(n * p for n, p in zip(numeros[:posicao], pesos, strict=True))
        verificador = 0 if soma % 11 < 2 else 11 - soma % 11
        if numeros[posicao] != verificador:
            return False
    return True


class Fundo(HandlerCotado):
    slug = "fundo"
    nome = "Fundo de investimento"
    descricao = "Fundos de renda fixa, multimercado, ações ou cambiais, cotados pela CVM."
    moedas_aceitas = ("BRL",)
    provider = "cvm"
    campos_identificacao: ClassVar[frozenset[str]] = frozenset({"cnpj"})
    campos = (
        CampoEspecifico(
            nome="cnpj",
            rotulo="CNPJ do fundo",
            tipo=TipoCampo.TEXTO,
            tamanho_maximo=18,
            ajuda="Usado para buscar o valor da cota na CVM.",
        ),
        CampoEspecifico(
            nome="classe",
            rotulo="Classe",
            tipo=TipoCampo.ESCOLHA,
            obrigatorio=False,
            opcoes=(
                Opcao("renda_fixa", "Renda fixa"),
                Opcao("multimercado", "Multimercado"),
                Opcao("acoes", "Ações"),
                Opcao("cambial", "Cambial"),
                Opcao("outro", "Outro"),
            ),
        ),
    )

    def regras_adicionais(self, metadados: Metadados) -> list[DetalheCampo]:
        cnpj = str(metadados["cnpj"])
        if not cnpj_valido(cnpj):
            return [DetalheCampo("cnpj", "CNPJ inválido.")]
        metadados["cnpj"] = _SO_DIGITOS.sub("", cnpj)
        return []
