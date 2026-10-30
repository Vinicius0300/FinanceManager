"""Movimentação única: o ativo é escolhido **ou criado** junto com a transação.

Regras (Parte 4.1):
- Informe ``ativo_id`` (ativo já cadastrado) **ou** ``novo_ativo`` (nunca os dois).
- ``novo_ativo`` passa pela validação normal do cadastro e pela **deduplicação** do tipo
  (``HandlerTipoAtivo.mesma_identidade``): se já existir o mesmo ativo (ticker, CNPJ,
  id da cripto, título + vencimento, a poupança), ele é reaproveitado.
- Só compra e aporte criam ativo: venda, resgate e provento exigem um ativo existente.
- Renda fixa com os mesmos emissor, indexador, taxa e vencimento de um título existente
  (``semelhante``) responde **409 ``ativo_semelhante``** sem gravar; o reenvio com
  ``usar_ativo_id`` grava como aporte nesse título e com ``confirmar_novo`` cria outro.
- A transação segue as regras de sempre (venda maior que a posição é recusada; saldo
  insuficiente devolve aviso). Quem chama desfaz tudo se algo falhar: o ativo criado
  nunca fica órfão (mesma unidade de trabalho).
"""

from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import TipoTransacao
from app.domain.erros import ConflitoError, DetalheCampo, ValidacaoError
from app.repositories import modelos as m
from app.services import transacoes as servico_transacoes
from app.services.cadastros import (
    NovoAtivo,
    ativo_identico,
    ativos_semelhantes,
    gravar_ativo_novo,
    obter_ativo,
    preparar_ativo,
)

OPERACOES_QUE_CRIAM = frozenset({TipoTransacao.COMPRA, TipoTransacao.APORTE})


class AtivoSemelhanteError(ConflitoError):
    """Já existe um investimento com os mesmos dados (o usuário decide somar ou separar)."""

    codigo = "ativo_semelhante"


@dataclass(frozen=True)
class NovaMovimentacao:
    transacao: servico_transacoes.NovaTransacao  # ``ativo_id`` é ignorado se houver novo
    ativo_id: int | None = None
    novo_ativo: NovoAtivo | None = None
    usar_ativo_id: int | None = None  # resposta ao 409: aporte no título existente
    confirmar_novo: bool = False  # resposta ao 409: cria um título separado


@dataclass(frozen=True)
class ResultadoMovimentacao:
    resultado: servico_transacoes.ResultadoTransacao
    ativo: m.Ativo
    ativo_criado: bool


def _resumo(ativo: m.Ativo) -> str:
    partes = [ativo.nome]
    for campo in ("indexador", "taxa", "vencimento"):
        if campo in ativo.metadados:
            partes.append(f"{campo}: {ativo.metadados[campo]}")
    return " · ".join(partes)


def _semelhante_escolhido(
    sessao: Session, usar_ativo_id: int, semelhantes: list[m.Ativo]
) -> m.Ativo:
    escolhido = obter_ativo(sessao, usar_ativo_id)
    if escolhido.id not in {a.id for a in semelhantes}:
        mensagem = "O ativo escolhido não tem os mesmos dados do novo título."
        raise ValidacaoError(mensagem, [DetalheCampo("usar_ativo_id", mensagem)])
    return escolhido


def _resolver_ativo(
    sessao: Session, dados: NovaMovimentacao, registro: RegistroTiposAtivo
) -> tuple[m.Ativo, bool]:
    if (dados.ativo_id is None) == (dados.novo_ativo is None):
        mensagem = "Escolha um ativo cadastrado ou informe os dados de um novo."
        raise ValidacaoError(mensagem, [DetalheCampo("ativo_id", mensagem)])
    if dados.novo_ativo is None:
        return obter_ativo(sessao, dados.ativo_id or 0), False
    if dados.transacao.tipo not in OPERACOES_QUE_CRIAM:
        mensagem = "Venda, resgate e provento só podem ser feitos em um ativo já cadastrado."
        raise ValidacaoError(mensagem, [DetalheCampo("ativo_id", mensagem)])
    novo, handler = preparar_ativo(dados.novo_ativo, registro)
    existente = ativo_identico(sessao, novo, handler)
    if existente is not None:
        return existente, False
    if not dados.confirmar_novo:
        semelhantes = ativos_semelhantes(sessao, novo, handler)
        if dados.usar_ativo_id is not None:
            return _semelhante_escolhido(sessao, dados.usar_ativo_id, semelhantes), False
        if semelhantes:
            primeiro = semelhantes[0]
            raise AtivoSemelhanteError(
                f"Você já tem um título com os mesmos dados ({primeiro.nome}). "
                "Registrar como aporte nele ou criar um título separado?",
                [
                    DetalheCampo("ativo_id", str(primeiro.id)),
                    DetalheCampo("nome", primeiro.nome),
                    DetalheCampo("resumo", _resumo(primeiro)),
                ],
            )
    return gravar_ativo_novo(sessao, novo, handler), True


def registrar_movimentacao(
    sessao: Session,
    dados: NovaMovimentacao,
    *,
    aceitar_ajuste: bool = False,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> ResultadoMovimentacao:
    """Resolve (ou cria) o ativo e registra a transação nele, na transação de quem chama.

    Se o resultado trouxer aviso de saldo insuficiente, **quem chama deve desfazer** a
    unidade de trabalho (a API faz isso ao responder 409), descartando o ativo criado.
    """
    ativo, criado = _resolver_ativo(sessao, dados, registro)
    transacao = replace(dados.transacao, ativo_id=ativo.id)
    resultado = servico_transacoes.registrar_transacao(
        sessao, transacao, aceitar_ajuste=aceitar_ajuste, registro=registro
    )
    return ResultadoMovimentacao(resultado=resultado, ativo=ativo, ativo_criado=criado)
