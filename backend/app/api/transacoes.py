"""Transações (compra, venda, aporte, resgate, provento) e eventos corporativos.

**Saldo insuficiente:** compra/aporte (ou edição) que deixaria o caixa da instituição
negativo responde **409** (``saldo_insuficiente``) com ``detalhes`` (instituição, moeda,
data e valor que falta) e não grava nada. O front confirma reenviando com
``aceitar_ajuste=true``; aí a transação é gravada junto com um ``ajuste_saldo``.
"""

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, status

from app.api.dependencias import PROTEGIDO, Deslocamento, Limite, SessaoDep, respostas
from app.api.schemas import Modelo, Numero, Pagina
from app.core.errors import AplicacaoError
from app.domain.enums import SubtipoProvento, TipoEvento, TipoTransacao
from app.domain.erros import ConflitoError, DetalheCampo
from app.domain.numeros import arredondar_moeda, formatar_dinheiro, texto_decimal
from app.domain.tempo import formatar_data
from app.repositories import modelos as m
from app.services import transacoes as servico
from app.services.cadastros import obter_instituicao

router = APIRouter(prefix="/api", tags=["transações"], dependencies=PROTEGIDO)


class SaldoInsuficienteApiError(ConflitoError):
    """409 com os detalhes do saldo que falta (o front pede confirmação)."""

    codigo = "saldo_insuficiente"


class TransacaoEntrada(Modelo):
    ativo_id: int
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


class MovimentoResumo(Modelo):
    id: int
    tipo: str
    valor: Numero


class TransacaoSaida(Modelo):
    id: int
    ativo_id: int
    instituicao_id: int
    tipo: TipoTransacao
    data: date
    quantidade: Numero | None
    preco_unitario: Numero | None
    valor: Numero | None
    taxas: Numero
    moeda: str
    cambio: Numero
    subtipo_provento: SubtipoProvento | None
    imposto_retido: Numero
    observacao: str | None
    criado_em: datetime
    movimentos: list[MovimentoResumo]


class EventoEntrada(Modelo):
    ativo_id: int
    tipo: TipoEvento
    data: date
    proporcao_de: int
    proporcao_para: int
    custo_unitario: Numero = Decimal(0)
    cambio: Numero | None = None
    observacao: str | None = None


class EventoSaida(Modelo):
    id: int
    ativo_id: int
    tipo: TipoEvento
    data: date
    proporcao_de: int
    proporcao_para: int
    custo_unitario: Numero
    cambio: Numero
    observacao: str | None
    criado_em: datetime


def _transacao(transacao: m.Transacao) -> TransacaoSaida:
    return TransacaoSaida(
        id=transacao.id,
        ativo_id=transacao.ativo_id,
        instituicao_id=transacao.instituicao_id,
        tipo=transacao.tipo,
        data=transacao.data,
        quantidade=transacao.quantidade,
        preco_unitario=transacao.preco_unitario,
        valor=transacao.valor,
        taxas=transacao.taxas,
        moeda=transacao.moeda,
        cambio=transacao.cambio,
        subtipo_provento=transacao.subtipo_provento,
        imposto_retido=transacao.imposto_retido,
        observacao=transacao.observacao,
        criado_em=transacao.criado_em,
        movimentos=[
            MovimentoResumo(id=mov.id, tipo=mov.tipo.value, valor=mov.valor)
            for mov in transacao.movimentos
        ],
    )


def _evento(evento: m.EventoCorporativo) -> EventoSaida:
    return EventoSaida(
        id=evento.id,
        ativo_id=evento.ativo_id,
        tipo=evento.tipo,
        data=evento.data,
        proporcao_de=evento.proporcao_de,
        proporcao_para=evento.proporcao_para,
        custo_unitario=evento.custo_unitario,
        cambio=evento.cambio,
        observacao=evento.observacao,
        criado_em=evento.criado_em,
    )


def _nova(dados: TransacaoEntrada) -> servico.NovaTransacao:
    return servico.NovaTransacao(
        ativo_id=dados.ativo_id,
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
    )


def _resultado(sessao: SessaoDep, resultado: servico.ResultadoTransacao) -> TransacaoSaida:
    if resultado.aviso is not None:
        aviso = resultado.aviso
        instituicao = obter_instituicao(sessao, aviso.instituicao_id)
        falta = arredondar_moeda(aviso.valor_faltante)
        raise SaldoInsuficienteApiError(
            f"Saldo insuficiente em {instituicao.nome} ({aviso.moeda}) em "
            f"{formatar_data(aviso.data)}: faltam {formatar_dinheiro(falta)} {aviso.moeda}. "
            "Confirme para registrar mesmo assim com um ajuste de saldo "
            "(depósito não informado).",
            [
                DetalheCampo("instituicao_id", str(aviso.instituicao_id)),
                DetalheCampo("instituicao", instituicao.nome),
                DetalheCampo("moeda", aviso.moeda),
                DetalheCampo("data", aviso.data.isoformat()),
                DetalheCampo("valor_faltante", texto_decimal(falta)),
            ],
        )
    if resultado.transacao is None:  # pragma: no cover - sem aviso, sempre há transação
        raise AplicacaoError(500, "erro_interno", "Transação não gravada.")
    return _transacao(resultado.transacao)


RESPOSTAS_TRANSACAO = respostas(404, 409, 422)


@router.get(
    "/transacoes",
    response_model=Pagina[TransacaoSaida],
    summary="Lista transações com filtros (mais recentes primeiro)",
    responses=respostas(),
)
def listar_transacoes(
    sessao: SessaoDep,
    ativo_id: int | None = None,
    instituicao_id: int | None = None,
    tipo: TipoTransacao | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
) -> Pagina[TransacaoSaida]:
    pagina = servico.listar_transacoes(
        sessao,
        ativo_id=ativo_id,
        instituicao_id=instituicao_id,
        tipo=tipo,
        inicio=inicio,
        fim=fim,
        limite=limite,
        deslocamento=deslocamento,
    )
    return Pagina[TransacaoSaida](
        itens=[_transacao(t) for t in pagina.itens],
        total=pagina.total,
        limite=limite,
        deslocamento=deslocamento,
    )


@router.post(
    "/transacoes",
    response_model=TransacaoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Registra uma transação",
    description=(
        "Se o caixa da instituição ficaria negativo, responde 409 `saldo_insuficiente` sem "
        "gravar. Reenvie com `aceitar_ajuste=true` para gravar com um ajuste de saldo."
    ),
    responses=RESPOSTAS_TRANSACAO,
)
def criar_transacao(dados: TransacaoEntrada, sessao: SessaoDep) -> TransacaoSaida:
    resultado = servico.registrar_transacao(
        sessao, _nova(dados), aceitar_ajuste=dados.aceitar_ajuste
    )
    return _resultado(sessao, resultado)


@router.get(
    "/transacoes/{transacao_id}",
    response_model=TransacaoSaida,
    summary="Detalha uma transação",
    responses=respostas(404),
)
def obter_transacao(transacao_id: int, sessao: SessaoDep) -> TransacaoSaida:
    return _transacao(servico.obter_transacao(sessao, transacao_id))


@router.put(
    "/transacoes/{transacao_id}",
    response_model=TransacaoSaida,
    summary="Substitui uma transação e reprocessa a posição",
    description="Mesmas regras do registro, inclusive o 409 de saldo insuficiente.",
    responses=RESPOSTAS_TRANSACAO,
)
def editar_transacao(
    transacao_id: int, dados: TransacaoEntrada, sessao: SessaoDep
) -> TransacaoSaida:
    resultado = servico.editar_transacao(
        sessao, transacao_id, _nova(dados), aceitar_ajuste=dados.aceitar_ajuste
    )
    return _resultado(sessao, resultado)


@router.delete(
    "/transacoes/{transacao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui uma transação (recusa se algo ficar inválido)",
    responses=respostas(404, 422),
)
def excluir_transacao(transacao_id: int, sessao: SessaoDep) -> None:
    servico.excluir_transacao(sessao, transacao_id)


@router.get(
    "/eventos-corporativos",
    response_model=list[EventoSaida],
    summary="Lista eventos corporativos (mais recentes primeiro)",
    responses=respostas(),
)
def listar_eventos(sessao: SessaoDep, ativo_id: int | None = None) -> list[EventoSaida]:
    return [_evento(e) for e in servico.listar_eventos(sessao, ativo_id)]


def _novo_evento(dados: EventoEntrada) -> servico.NovoEvento:
    return servico.NovoEvento(
        ativo_id=dados.ativo_id,
        tipo=dados.tipo,
        data=dados.data,
        proporcao_de=dados.proporcao_de,
        proporcao_para=dados.proporcao_para,
        custo_unitario=dados.custo_unitario,
        cambio=dados.cambio,
        observacao=dados.observacao,
    )


@router.post(
    "/eventos-corporativos",
    response_model=EventoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Registra desdobramento, grupamento ou bonificação",
    responses=RESPOSTAS_TRANSACAO,
)
def criar_evento(dados: EventoEntrada, sessao: SessaoDep) -> EventoSaida:
    return _evento(servico.registrar_evento(sessao, _novo_evento(dados)))


@router.put(
    "/eventos-corporativos/{evento_id}",
    response_model=EventoSaida,
    summary="Substitui um evento corporativo e reprocessa o ativo",
    responses=RESPOSTAS_TRANSACAO,
)
def editar_evento(evento_id: int, dados: EventoEntrada, sessao: SessaoDep) -> EventoSaida:
    return _evento(servico.editar_evento(sessao, evento_id, _novo_evento(dados)))


@router.delete(
    "/eventos-corporativos/{evento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um evento corporativo (recusa se algo ficar inválido)",
    responses=respostas(404, 422),
)
def excluir_evento(evento_id: int, sessao: SessaoDep) -> None:
    servico.excluir_evento(sessao, evento_id)
