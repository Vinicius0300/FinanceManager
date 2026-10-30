"""Movimentação única (Parte 4.1): escolhe ou cria o ativo e registra a transação juntos.

Atômica: qualquer erro (inclusive os 409) desfaz tudo, então um ativo novo nunca fica
órfão. Respostas 409:
- ``saldo_insuficiente``: reenvie com ``aceitar_ajuste=true`` (igual a ``/transacoes``);
- ``ativo_semelhante`` (renda fixa com os mesmos dados de um título existente): reenvie com
  ``usar_ativo_id`` (aporte nele) ou ``confirmar_novo=true`` (título separado).
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, status

from app.api.ativos import AtivoEntrada, AtivoSaida, coletar_depois, saida_ativo
from app.api.dependencias import PROTEGIDO, AgendadorDep, SessaoDep, respostas
from app.api.schemas import Modelo, Numero
from app.api.transacoes import TransacaoSaida, resposta_transacao
from app.domain.enums import SubtipoProvento, TipoTransacao
from app.services import movimentacoes as servico
from app.services.cadastros import NovoAtivo
from app.services.transacoes import NovaTransacao

router = APIRouter(prefix="/api", tags=["movimentações"], dependencies=PROTEGIDO)


class MovimentacaoEntrada(Modelo):
    ativo_id: int | None = None
    novo_ativo: AtivoEntrada | None = None
    usar_ativo_id: int | None = None
    confirmar_novo: bool = False
    instituicao_id: int
    tipo: TipoTransacao
    data: date
    quantidade: Numero | None = None
    preco_unitario: Numero | None = None
    valor: Numero | None = None
    taxas: Numero = Decimal(0)
    cambio: Numero | None = None
    subtipo_provento: SubtipoProvento | None = None
    imposto_retido: Numero = Decimal(0)
    observacao: str | None = None
    aceitar_ajuste: bool = False


class MovimentacaoSaida(Modelo):
    transacao: TransacaoSaida
    ativo: AtivoSaida
    ativo_criado: bool


def _nova(dados: MovimentacaoEntrada) -> servico.NovaMovimentacao:
    novo = dados.novo_ativo
    return servico.NovaMovimentacao(
        transacao=NovaTransacao(
            ativo_id=dados.ativo_id or 0,  # substituído pelo ativo resolvido
            instituicao_id=dados.instituicao_id,
            tipo=dados.tipo,
            data=dados.data,
            quantidade=dados.quantidade,
            preco_unitario=dados.preco_unitario,
            valor=dados.valor,
            taxas=dados.taxas,
            cambio=dados.cambio,
            subtipo_provento=dados.subtipo_provento,
            imposto_retido=dados.imposto_retido,
            observacao=dados.observacao,
        ),
        ativo_id=dados.ativo_id,
        novo_ativo=None
        if novo is None
        else NovoAtivo(
            tipo=novo.tipo,
            nome=novo.nome,
            simbolo=novo.simbolo,
            moeda=novo.moeda,
            simbolo_externo=novo.simbolo_externo,
            metadados=novo.metadados,
        ),
        usar_ativo_id=dados.usar_ativo_id,
        confirmar_novo=dados.confirmar_novo,
    )


@router.post(
    "/movimentacoes",
    response_model=MovimentacaoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma movimentação, criando o ativo se ele ainda não existir",
    description=(
        "Informe `ativo_id` ou `novo_ativo`. O ativo novo passa pela deduplicação do tipo "
        "(o mesmo ticker, CNPJ, id de cripto ou título é reaproveitado). Só compra e aporte "
        "criam ativo. 409 `saldo_insuficiente`: reenvie com `aceitar_ajuste=true`. "
        "409 `ativo_semelhante`: reenvie com `usar_ativo_id` ou `confirmar_novo=true`."
    ),
    responses=respostas(404, 409, 422),
)
def registrar_movimentacao(
    dados: MovimentacaoEntrada,
    sessao: SessaoDep,
    agendador: AgendadorDep,
    tarefas: BackgroundTasks,
) -> MovimentacaoSaida:
    resultado = servico.registrar_movimentacao(
        sessao, _nova(dados), aceitar_ajuste=dados.aceitar_ajuste
    )
    transacao = resposta_transacao(sessao, resultado.resultado)  # 409 desfaz o ativo novo
    if resultado.ativo_criado:
        coletar_depois(resultado.ativo, agendador, tarefas)
    return MovimentacaoSaida(
        transacao=transacao,
        ativo=saida_ativo(resultado.ativo),
        ativo_criado=resultado.ativo_criado,
    )
