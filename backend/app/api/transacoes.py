"""Transações (compra, venda, aporte, resgate, provento) e eventos corporativos.

**Saldo insuficiente:** compra/aporte (ou edição) que deixaria o caixa da instituição
negativo responde **409** (``saldo_insuficiente``) com ``detalhes`` (instituição, moeda,
data e valor que falta) e não grava nada. O front confirma reenviando com
``aceitar_ajuste=true``; aí a transação é gravada junto com um ``ajuste_saldo``.

**Histórico (Parte 4):** a listagem aceita os filtros da tela Movimentações e cada
transação traz o valor total, o resultado (lucro/prejuízo realizado da venda ou resgate) e
a situação do ativo. ``/transacoes/resumo`` devolve os totais dos cartões, a série mensal
e a visão por ativo; ``/transacoes/exportar`` grava a planilha Excel com os mesmos filtros.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencias import (
    PROTEGIDO,
    Deslocamento,
    HojeDep,
    Limite,
    SessaoDep,
    respostas,
)
from app.api.schemas import Modelo, Numero, Pagina
from app.core.errors import AplicacaoError
from app.domain.enums import SubtipoProvento, TipoEvento, TipoTransacao
from app.domain.erros import ConflitoError, DetalheCampo, ValidacaoError
from app.domain.historico import GrupoAtivo, OperacaoHistorico, SituacaoPosicao, TotaisHistorico
from app.domain.numeros import arredondar_moeda, formatar_dinheiro, texto_decimal
from app.domain.tempo import formatar_data
from app.repositories import modelos as m
from app.services import exportacao, historico
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
    valor_total: Numero
    valor_total_brl: Numero
    taxas_brl: Numero
    imposto_retido_brl: Numero
    resultado: Numero | None
    resultado_brl: Numero | None
    situacao: SituacaoPosicao


class TotaisHistoricoSaida(Modelo):
    operacoes: int
    total_comprado: Numero
    total_vendido: Numero
    lucro_realizado: Numero
    proventos_liquidos: Numero
    impostos_retidos: Numero
    taxas: Numero
    operacoes_com_taxas: int


class PontoMensalSaida(Modelo):
    mes: date
    compras: Numero
    vendas: Numero
    proventos: Numero


class GrupoInstituicaoSaida(Modelo):
    instituicao_id: int
    situacao: SituacaoPosicao
    totais: TotaisHistoricoSaida


class GrupoAtivoSaida(Modelo):
    ativo_id: int
    situacao: SituacaoPosicao
    totais: TotaisHistoricoSaida
    instituicoes: list[GrupoInstituicaoSaida]


class ResumoHistoricoSaida(Modelo):
    totais: TotaisHistoricoSaida
    total_sem_filtros: int
    inicio: date | None
    fim: date | None
    serie: list[PontoMensalSaida]
    por_ativo: list[GrupoAtivoSaida]


class ExportacaoEntrada(Modelo):
    caminho: str


class ExportacaoSaida(Modelo):
    caminho: str
    linhas: int


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


def _transacao(
    transacao: m.Transacao, operacao: OperacaoHistorico, situacao: SituacaoPosicao
) -> TransacaoSaida:
    resultado = operacao.resultado
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
        valor_total=arredondar_moeda(operacao.valor_total),
        valor_total_brl=arredondar_moeda(operacao.valor_total_brl),
        taxas_brl=arredondar_moeda(operacao.taxas_brl),
        imposto_retido_brl=arredondar_moeda(operacao.imposto_retido_brl),
        resultado=None if resultado is None else arredondar_moeda(resultado.resultado),
        resultado_brl=None if resultado is None else arredondar_moeda(resultado.resultado_brl),
        situacao=situacao,
    )


def _transacao_unica(sessao: SessaoDep, transacao: m.Transacao) -> TransacaoSaida:
    operacao, situacao = historico.operacao_da_transacao(sessao, transacao)
    return _transacao(transacao, operacao, situacao)


def _totais(totais: TotaisHistorico) -> TotaisHistoricoSaida:
    return TotaisHistoricoSaida(
        operacoes=totais.operacoes,
        total_comprado=arredondar_moeda(totais.total_comprado),
        total_vendido=arredondar_moeda(totais.total_vendido),
        lucro_realizado=arredondar_moeda(totais.lucro_realizado),
        proventos_liquidos=arredondar_moeda(totais.proventos_liquidos),
        impostos_retidos=arredondar_moeda(totais.impostos_retidos),
        taxas=arredondar_moeda(totais.taxas),
        operacoes_com_taxas=totais.operacoes_com_taxas,
    )


def _grupo(grupo: GrupoAtivo) -> GrupoAtivoSaida:
    return GrupoAtivoSaida(
        ativo_id=grupo.ativo_id,
        situacao=grupo.situacao,
        totais=_totais(grupo.totais),
        instituicoes=[
            GrupoInstituicaoSaida(
                instituicao_id=i.instituicao_id, situacao=i.situacao, totais=_totais(i.totais)
            )
            for i in grupo.instituicoes
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


def resposta_transacao(sessao: SessaoDep, resultado: servico.ResultadoTransacao) -> TransacaoSaida:
    """Serializa o resultado; aviso de saldo insuficiente vira 409 (a sessão é desfeita)."""
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
    return _transacao_unica(sessao, resultado.transacao)


def filtros_historico(
    ativo_id: int | None = None,
    instituicao_id: int | None = None,
    tipo: Annotated[
        TipoTransacao | None, Query(description="Uma operação (use `tipos` para várias).")
    ] = None,
    tipos: Annotated[
        list[TipoTransacao] | None,
        Query(description="Operações aceitas (repita o parâmetro). Vazio = todas."),
    ] = None,
    tipo_ativo: Annotated[
        str | None, Query(max_length=40, description="Slug do tipo de ativo.")
    ] = None,
    moeda: Annotated[
        str | None, Query(min_length=3, max_length=3, description="Moeda do ativo (BRL, USD).")
    ] = None,
    busca: Annotated[
        str | None, Query(max_length=60, description="Parte do símbolo ou do nome do ativo.")
    ] = None,
    inicio: date | None = None,
    fim: date | None = None,
    situacao: Annotated[
        SituacaoPosicao | None,
        Query(
            description=(
                "Com `instituicao_id`, situação da posição naquela instituição; sem ele, "
                "do ativo somando todas as instituições."
            )
        ),
    ] = None,
    apenas_prejuizo: Annotated[
        bool, Query(description="Só vendas/resgates com resultado negativo.")
    ] = False,
    apenas_com_custos: Annotated[
        bool, Query(description="Só operações com taxas ou imposto retido.")
    ] = False,
) -> historico.FiltroHistorico:
    """Filtros comuns à listagem, ao resumo e à exportação do histórico."""
    if inicio is not None and fim is not None and inicio > fim:
        raise ValidacaoError(
            "A data inicial não pode ser depois da final.",
            [DetalheCampo("inicio", "Deve ser anterior ou igual à data final.")],
        )
    termo = busca.strip() if busca else None
    return historico.FiltroHistorico(
        ativo_id=ativo_id,
        instituicao_id=instituicao_id,
        tipo_ativo=tipo_ativo or None,
        moeda=moeda.upper() if moeda else None,
        busca=termo or None,
        tipos=historico.tipos_efetivos(tipo, tipos),
        inicio=inicio,
        fim=fim,
        situacao=situacao,
        apenas_prejuizo=apenas_prejuizo,
        apenas_com_custos=apenas_com_custos,
    )


FiltrosDep = Annotated[historico.FiltroHistorico, Depends(filtros_historico)]
RESPOSTAS_TRANSACAO = respostas(404, 409, 422)


@router.get(
    "/transacoes",
    response_model=Pagina[TransacaoSaida],
    summary="Lista transações com os filtros do histórico",
    description=(
        "Ordenação por `ordem` (padrão: data) e `direcao` (padrão: desc); itens sem valor "
        "no campo ordenado vão para o fim. Cada item traz valor total, resultado "
        "(vendas/resgates) e situação do ativo."
    ),
    responses=respostas(422),
)
def listar_transacoes(
    sessao: SessaoDep,
    filtro: FiltrosDep,
    ordem: historico.CampoOrdem = historico.CampoOrdem.DATA,
    direcao: historico.Direcao = historico.Direcao.DESC,
    limite: Limite = 50,
    deslocamento: Deslocamento = 0,
) -> Pagina[TransacaoSaida]:
    itens = historico.consultar(sessao, filtro, ordem, direcao).itens
    pagina = itens[deslocamento : deslocamento + limite]
    return Pagina[TransacaoSaida](
        itens=[_transacao(i.transacao, i.operacao, i.situacao) for i in pagina],
        total=len(itens),
        limite=limite,
        deslocamento=deslocamento,
    )


@router.get(
    "/transacoes/resumo",
    response_model=ResumoHistoricoSaida,
    summary="Totais, série mensal e visão por ativo do histórico filtrado",
    description=(
        "Valores em BRL (câmbio de cada operação), arredondados a centavos. A série vai do "
        "início do filtro (ou da operação mais antiga) até o fim do filtro (ou hoje), um "
        "ponto por mês, inclusive os meses sem operação."
    ),
    responses=respostas(422),
)
def obter_resumo_historico(
    sessao: SessaoDep, filtro: FiltrosDep, hoje: HojeDep
) -> ResumoHistoricoSaida:
    resumo = historico.resumir(sessao, filtro, hoje)
    return ResumoHistoricoSaida(
        totais=_totais(resumo.totais),
        total_sem_filtros=resumo.total_sem_filtros,
        inicio=resumo.inicio,
        fim=resumo.fim,
        serie=[
            PontoMensalSaida(
                mes=p.mes,
                compras=arredondar_moeda(p.compras),
                vendas=arredondar_moeda(p.vendas),
                proventos=arredondar_moeda(p.proventos),
            )
            for p in resumo.serie
        ],
        por_ativo=[_grupo(g) for g in resumo.por_ativo],
    )


@router.post(
    "/transacoes/exportar",
    response_model=ExportacaoSaida,
    summary="Grava o histórico filtrado numa planilha Excel (.xlsx)",
    description=(
        "Mesmos filtros e ordem da listagem (todas as páginas). `caminho` é o arquivo "
        "escolhido no diálogo de salvar (absoluto, .xlsx, pasta existente)."
    ),
    responses=respostas(422),
)
def exportar_transacoes(
    dados: ExportacaoEntrada,
    sessao: SessaoDep,
    filtro: FiltrosDep,
    hoje: HojeDep,
    ordem: historico.CampoOrdem = historico.CampoOrdem.DATA,
    direcao: historico.Direcao = historico.Direcao.DESC,
) -> ExportacaoSaida:
    arquivo = exportacao.exportar_historico(sessao, filtro, dados.caminho, hoje, ordem, direcao)
    return ExportacaoSaida(caminho=str(arquivo.caminho), linhas=arquivo.linhas)


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
    return resposta_transacao(sessao, resultado)


@router.get(
    "/transacoes/{transacao_id}",
    response_model=TransacaoSaida,
    summary="Detalha uma transação",
    responses=respostas(404),
)
def obter_transacao(transacao_id: int, sessao: SessaoDep) -> TransacaoSaida:
    return _transacao_unica(sessao, servico.obter_transacao(sessao, transacao_id))


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
    return resposta_transacao(sessao, resultado)


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
