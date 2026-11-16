"""Casos de uso de receitas e despesas (orçamento pessoal).

Todo lançamento pertence a uma instituição e movimenta a conta em **BRL** dela:
receita credita (``credito_receita``) e despesa debita (``debito_despesa``). O saldo
nunca fica negativo em nenhum dia (``domain/conta_corrente.deficit``):

- despesa nova, aumentada, antecipada ou levada para outra instituição que deixaria o
  caixa negativo devolve um **aviso** (409) sem gravar nada; com ``aceitar_ajuste=True``
  grava a despesa e um ``ajuste_saldo`` **ligado a ela** (refeito na edição, excluído junto);
- excluir ou alterar uma **receita** de forma que o caixa fique negativo é **recusado**
  (422, sem ajuste), como excluir uma venda ou um depósito;
- tarifas de transferência (``transferencia_id`` preenchido) só mudam pela transferência.

A listagem junta os lançamentos e as transferências em BRL (duas linhas por
transferência, só leitura); os totais e as categorias ignoram as transferências.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.conta_corrente import (
    MENSAGEM_SALDO_INSUFICIENTE,
    LancamentoCaixa,
    deficit,
    movimento_do_lancamento,
    valor_com_sinal,
)
from app.domain.enums import TipoLancamento, TipoMovimento
from app.domain.erros import ConflitoError, NaoEncontradoError, OperacaoNaoPermitidaError, exigir
from app.domain.lancamentos import (
    Lancamento,
    ResumoInstituicao,
    ResumoMensal,
    TotalCategoria,
    TransferenciaMes,
    resumo_mensal,
    resumo_por_instituicao,
    totais_por_categoria,
    validar_mes,
)
from app.domain.numeros import CASAS_MOEDA, ZERO, exigir_casas
from app.domain.tempo import primeiro_dia_do_proximo_mes
from app.domain.textos import texto_obrigatorio, texto_opcional
from app.repositories import modelos as m
from app.repositories.contas import RepositorioMovimentos
from app.repositories.lancamentos import RepositorioCategorias, RepositorioLancamentos
from app.repositories.transferencias import RepositorioTransferencias
from app.services.cadastros import obter_instituicao
from app.services.caixa import (
    DESCRICAO_AJUSTE,
    AvisoSaldoInsuficiente,
    exigir_sem_deficit,
    lancamentos,
    movimentos_da_conta,
    obter_conta,
    obter_ou_criar_conta,
)

MOEDA_LANCAMENTOS = "BRL"
TAMANHO_NOME_CATEGORIA = 80
TAMANHO_DESCRICAO = 200
TAMANHO_OBSERVACAO = 500
MENSAGEM_TARIFA = (
    "Esta despesa é a tarifa de uma transferência: altere ou exclua a transferência em "
    "Movimentações → Caixa."
)


# ------------------------------------------------------------- Categorias


def _nome_categoria(nome: str) -> str:
    return texto_obrigatorio(
        nome, "nome", TAMANHO_NOME_CATEGORIA, mensagem_vazio="Informe o nome da categoria."
    )


def criar_categoria(sessao: Session, nome: str, tipo: TipoLancamento) -> m.Categoria:
    nome_limpo = _nome_categoria(nome)
    repositorio = RepositorioCategorias(sessao)
    if repositorio.por_nome(nome_limpo, tipo) is not None:
        raise ConflitoError(f"Já existe a categoria {nome_limpo!r} de {tipo.value}.")
    return repositorio.adicionar(m.Categoria(nome=nome_limpo, tipo=tipo))


def obter_categoria(sessao: Session, categoria_id: int) -> m.Categoria:
    categoria = RepositorioCategorias(sessao).obter(categoria_id)
    if categoria is None:
        raise NaoEncontradoError(f"Categoria {categoria_id} não encontrada.")
    return categoria


def listar_categorias(sessao: Session, tipo: TipoLancamento | None = None) -> Sequence[m.Categoria]:
    categorias = RepositorioCategorias(sessao).listar()
    return [c for c in categorias if c.tipo is tipo] if tipo else categorias


def renomear_categoria(sessao: Session, categoria_id: int, nome: str) -> m.Categoria:
    """Só o nome muda: o tipo (receita/despesa) precisa casar com os lançamentos dela."""
    categoria = obter_categoria(sessao, categoria_id)
    nome_limpo = _nome_categoria(nome)
    outra = RepositorioCategorias(sessao).por_nome(nome_limpo, categoria.tipo)
    if outra is not None and outra.id != categoria.id:
        raise ConflitoError(f"Já existe a categoria {nome_limpo!r} de {categoria.tipo.value}.")
    categoria.nome = nome_limpo
    sessao.flush()
    return categoria


def excluir_categoria(sessao: Session, categoria_id: int) -> None:
    repositorio = RepositorioCategorias(sessao)
    categoria = obter_categoria(sessao, categoria_id)
    if RepositorioLancamentos(sessao).existe_na_categoria(categoria_id):
        raise OperacaoNaoPermitidaError(
            "A categoria tem lançamentos. Mova-os para outra categoria antes de excluir."
        )
    repositorio.remover(categoria)


# ------------------------------------------------------------- Lançamentos


@dataclass(frozen=True)
class NovoLancamento:
    tipo: TipoLancamento
    data: date
    descricao: str
    valor: Decimal
    categoria_id: int | None = None
    observacao: str | None = None
    instituicao_id: int = field(kw_only=True)


@dataclass(frozen=True)
class ResultadoLancamento:
    lancamento: m.Lancamento | None
    aviso: AvisoSaldoInsuficiente | None = None
    ajuste: m.MovimentoConta | None = None


def validar_categoria(sessao: Session, categoria_id: int | None, tipo: TipoLancamento) -> None:
    if categoria_id is None:
        return
    categoria = obter_categoria(sessao, categoria_id)
    exigir(
        categoria.tipo is tipo,
        "categoria_id",
        f"A categoria {categoria.nome!r} é de {categoria.tipo.value}, não de {tipo.value}.",
    )


def _validar_lancamento(sessao: Session, dados: NovoLancamento) -> tuple[str, str | None]:
    """Valida os dados e devolve (descrição, observação) já limpos."""
    descricao = texto_obrigatorio(
        dados.descricao, "descricao", TAMANHO_DESCRICAO, mensagem_vazio="Informe a descrição."
    )
    exigir(dados.valor > ZERO, "valor", "O valor deve ser maior que zero.")
    exigir_casas(dados.valor, CASAS_MOEDA, "valor")
    observacao = texto_opcional(dados.observacao, "observacao", TAMANHO_OBSERVACAO)
    obter_instituicao(sessao, dados.instituicao_id)
    validar_categoria(sessao, dados.categoria_id, dados.tipo)
    return descricao, observacao


def _caixa_sem(
    sessao: Session, instituicao_id: int, lancamento_id: int | None
) -> list[LancamentoCaixa]:
    """Movimentos da conta BRL da instituição, sem os ligados a ``lancamento_id``."""
    conta = obter_conta(sessao, instituicao_id, MOEDA_LANCAMENTOS)
    if conta is None:
        return []
    return lancamentos(
        x
        for x in movimentos_da_conta(sessao, conta.id)
        if lancamento_id is None or x.lancamento_id != lancamento_id
    )


def efeito_no_caixa(tipo: TipoLancamento, data: date, valor: Decimal) -> LancamentoCaixa:
    return LancamentoCaixa(data, valor_com_sinal(movimento_do_lancamento(tipo), valor))


def _aviso(dados: NovoLancamento, faltante: Decimal) -> ResultadoLancamento:
    return ResultadoLancamento(
        lancamento=None,
        aviso=AvisoSaldoInsuficiente(
            mensagem=MENSAGEM_SALDO_INSUFICIENTE,
            instituicao_id=dados.instituicao_id,
            moeda=MOEDA_LANCAMENTOS,
            data=dados.data,
            valor_faltante=faltante,
        ),
    )


def _recusar_se_faltar(
    sessao: Session,
    instituicao_id: int,
    movimentos: list[LancamentoCaixa],
    a_partir_de: date,
    acao: str,
) -> None:
    """Recusa (422) com a mensagem do caixa: instituição, data e valor que falta."""
    if deficit(movimentos, a_partir_de) <= ZERO:
        return
    conta = obter_ou_criar_conta(sessao, instituicao_id, MOEDA_LANCAMENTOS)
    exigir_sem_deficit(conta, movimentos, a_partir_de, acao)


def gravar_movimentos_do_lancamento(
    sessao: Session, lancamento: m.Lancamento, faltante: Decimal = ZERO
) -> m.MovimentoConta | None:
    """Cria o movimento do lançamento e, se faltar saldo, o ajuste ligado a ele."""
    conta = obter_ou_criar_conta(sessao, lancamento.instituicao_id, MOEDA_LANCAMENTOS)
    movimentos = RepositorioMovimentos(sessao)
    movimentos.adicionar(
        m.MovimentoConta(
            conta_id=conta.id,
            lancamento_id=lancamento.id,
            tipo=movimento_do_lancamento(lancamento.tipo),
            data=lancamento.data,
            valor=lancamento.valor,
            descricao=lancamento.descricao,
        )
    )
    if faltante <= ZERO:
        return None
    return movimentos.adicionar(
        m.MovimentoConta(
            conta_id=conta.id,
            lancamento_id=lancamento.id,
            tipo=TipoMovimento.AJUSTE_SALDO,
            data=lancamento.data,
            valor=faltante,
            descricao=DESCRICAO_AJUSTE,
        )
    )


def registrar_lancamento(
    sessao: Session, dados: NovoLancamento, *, aceitar_ajuste: bool = False
) -> ResultadoLancamento:
    """Grava a receita ou despesa e o movimento no caixa (com aviso se faltar saldo).

    Ex.: caixa de 1.000 e despesa de 1.500 → aviso de 500; aceito, grava a despesa e um
    ajuste de 500, e o caixa fica em 0.
    """
    descricao, observacao = _validar_lancamento(sessao, dados)
    faltante = ZERO
    if dados.tipo is TipoLancamento.DESPESA:
        existentes = _caixa_sem(sessao, dados.instituicao_id, None)
        novo = efeito_no_caixa(dados.tipo, dados.data, dados.valor)
        faltante = deficit([*existentes, novo], dados.data)
        if faltante > ZERO and not aceitar_ajuste:
            return _aviso(dados, faltante)
    lancamento = RepositorioLancamentos(sessao).adicionar(
        m.Lancamento(
            tipo=dados.tipo,
            data=dados.data,
            descricao=descricao,
            valor=dados.valor,
            instituicao_id=dados.instituicao_id,
            categoria_id=dados.categoria_id,
            observacao=observacao,
        )
    )
    ajuste = gravar_movimentos_do_lancamento(sessao, lancamento, faltante)
    return ResultadoLancamento(lancamento=lancamento, ajuste=ajuste)


def obter_lancamento(sessao: Session, lancamento_id: int) -> m.Lancamento:
    lancamento = RepositorioLancamentos(sessao).obter(lancamento_id)
    if lancamento is None:
        raise NaoEncontradoError(f"Lançamento {lancamento_id} não encontrado.")
    return lancamento


def _obter_editavel(sessao: Session, lancamento_id: int) -> m.Lancamento:
    lancamento = obter_lancamento(sessao, lancamento_id)
    if lancamento.transferencia_id is not None:
        raise OperacaoNaoPermitidaError(MENSAGEM_TARIFA)
    return lancamento


def editar_lancamento(
    sessao: Session,
    lancamento_id: int,
    dados: NovoLancamento,
    *,
    aceitar_ajuste: bool = False,
) -> ResultadoLancamento:
    """Substitui o lançamento; o movimento e o ajuste antigos são refeitos.

    - Era **receita**: se o caixa (da instituição antiga ou da nova) ficar negativo, a
      edição é recusada (reduzir, adiar, trocar de instituição ou virar despesa).
    - Era **despesa**: a conta que perde a despesa só ganha saldo; na conta que recebe a
      despesa, falta de saldo vira aviso (e ajuste, se aceito), como num registro novo.
      Como o ajuste antigo também é refeito, alterar uma despesa que tinha ajuste pede a
      confirmação de novo.
    """
    original = _obter_editavel(sessao, lancamento_id)
    descricao, observacao = _validar_lancamento(sessao, dados)
    mesma_conta = original.instituicao_id == dados.instituicao_id
    inicio = min(original.data, dados.data) if mesma_conta else dados.data
    acao = (
        "Alterar esta receita"
        if original.tipo is TipoLancamento.RECEITA
        else "Alterar esta despesa"
    )
    if not mesma_conta:
        antiga = _caixa_sem(sessao, original.instituicao_id, original.id)
        _recusar_se_faltar(sessao, original.instituicao_id, antiga, original.data, acao)
    nova = [
        *_caixa_sem(sessao, dados.instituicao_id, original.id),
        efeito_no_caixa(dados.tipo, dados.data, dados.valor),
    ]
    faltante = deficit(nova, inicio)
    if faltante > ZERO:
        if original.tipo is TipoLancamento.RECEITA or dados.tipo is TipoLancamento.RECEITA:
            _recusar_se_faltar(sessao, dados.instituicao_id, nova, inicio, acao)
        # Despesa que tira o saldo: o ajuste na data dela precisa zerar o pior saldo.
        ajustado = [*nova, LancamentoCaixa(dados.data, faltante)]
        _recusar_se_faltar(sessao, dados.instituicao_id, ajustado, inicio, acao)
        if not aceitar_ajuste:
            return _aviso(dados, faltante)
    movimentos = RepositorioMovimentos(sessao)
    for movimento in movimentos.da_lancamento(original.id):
        movimentos.remover(movimento)
    sessao.expire(original, ["movimentos"])
    original.tipo = dados.tipo
    original.data = dados.data
    original.descricao = descricao
    original.valor = dados.valor
    original.instituicao_id = dados.instituicao_id
    original.categoria_id = dados.categoria_id
    original.observacao = observacao
    sessao.flush()
    sessao.expire(original, ["instituicao", "categoria"])
    ajuste = gravar_movimentos_do_lancamento(sessao, original, faltante)
    return ResultadoLancamento(lancamento=original, ajuste=ajuste)


def excluir_lancamento(sessao: Session, lancamento_id: int) -> None:
    """Exclui o lançamento, o movimento e o ajuste ligados (recusa se o caixa ficar < 0).

    Ex.: Nubank com 0, salário de 5.000 em 05/11 e aluguel de 2.000 em 10/11 → excluir o
    salário deixaria −2.000 a partir de 10/11: recusado.
    """
    lancamento = _obter_editavel(sessao, lancamento_id)
    restantes = _caixa_sem(sessao, lancamento.instituicao_id, lancamento.id)
    acao = (
        "Excluir esta receita"
        if lancamento.tipo is TipoLancamento.RECEITA
        else "Excluir esta despesa"
    )
    _recusar_se_faltar(sessao, lancamento.instituicao_id, restantes, lancamento.data, acao)
    RepositorioLancamentos(sessao).remover(lancamento)


# ------------------------------------------------------------- Listagem combinada

TAG_LANCAMENTO = "lancamento"
TAG_TARIFA = "tarifa"
TAG_TRANSFERENCIA_SAIDA = "transferencia_saida"
TAG_TRANSFERENCIA_ENTRADA = "transferencia_entrada"


@dataclass(frozen=True)
class LinhaLancamento:
    """Linha da tabela de Receitas e Despesas: um lançamento ou uma ponta de transferência.

    A saída de uma transferência aparece como despesa e a entrada como receita (só para
    exibição; não entram nos totais).
    """

    chave: str
    tag: str
    lancamento_id: int | None
    transferencia_id: int | None
    tipo: TipoLancamento
    data: date
    descricao: str
    valor: Decimal
    instituicao_id: int
    instituicao_nome: str
    categoria_id: int | None
    categoria_nome: str | None
    observacao: str | None
    criado_em: datetime
    editavel: bool


@dataclass(frozen=True)
class PaginaLancamentos:
    itens: Sequence[LinhaLancamento]
    total: int


def linha_do_lancamento(lancamento: m.Lancamento) -> LinhaLancamento:
    tarifa = lancamento.transferencia_id is not None
    return LinhaLancamento(
        chave=f"lancamento-{lancamento.id}",
        tag=TAG_TARIFA if tarifa else TAG_LANCAMENTO,
        lancamento_id=lancamento.id,
        transferencia_id=lancamento.transferencia_id,
        tipo=lancamento.tipo,
        data=lancamento.data,
        descricao=lancamento.descricao,
        valor=lancamento.valor,
        instituicao_id=lancamento.instituicao_id,
        instituicao_nome=lancamento.instituicao.nome,
        categoria_id=lancamento.categoria_id,
        categoria_nome=lancamento.categoria.nome if lancamento.categoria else None,
        observacao=lancamento.observacao,
        criado_em=lancamento.criado_em,
        editavel=not tarifa,
    )


def _com_descricao(texto: str, descricao: str | None) -> str:
    return f"{texto}: {descricao}" if descricao else texto


def linhas_da_transferencia(transferencia: m.Transferencia) -> list[LinhaLancamento]:
    """Saída (na origem) e entrada (no destino) de uma transferência, só para leitura."""

    def linha(saida: bool) -> LinhaLancamento:
        instituicao = transferencia.origem if saida else transferencia.destino
        texto = (
            f"Transferência para {transferencia.destino.nome}"
            if saida
            else f"Transferência de {transferencia.origem.nome}"
        )
        return LinhaLancamento(
            chave=f"transferencia-{transferencia.id}-{'saida' if saida else 'entrada'}",
            tag=TAG_TRANSFERENCIA_SAIDA if saida else TAG_TRANSFERENCIA_ENTRADA,
            lancamento_id=None,
            transferencia_id=transferencia.id,
            tipo=TipoLancamento.DESPESA if saida else TipoLancamento.RECEITA,
            data=transferencia.data,
            descricao=_com_descricao(texto, transferencia.descricao),
            valor=transferencia.valor,
            instituicao_id=instituicao.id,
            instituicao_nome=instituicao.nome,
            categoria_id=None,
            categoria_nome=None,
            observacao=None,
            criado_em=transferencia.criado_em,
            editavel=False,
        )

    return [linha(saida=True), linha(saida=False)]


def listar_lancamentos(
    sessao: Session,
    *,
    tipo: TipoLancamento | None = None,
    categoria_id: int | None = None,
    instituicao_id: int | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = 50,
    deslocamento: int = 0,
) -> PaginaLancamentos:
    """Lançamentos e transferências em BRL, do mais recente para o mais antigo.

    Filtros: ``tipo`` vale para a linha exibida (a saída de uma transferência conta como
    despesa e a entrada como receita); com ``categoria_id`` as transferências ficam de fora;
    ``instituicao_id`` é a instituição da linha. A paginação vale sobre a lista combinada
    (transferências em USD nunca aparecem aqui).
    """
    linhas = [
        linha_do_lancamento(x)
        for x in RepositorioLancamentos(sessao).filtrados(
            tipo=tipo,
            categoria_id=categoria_id,
            instituicao_id=instituicao_id,
            inicio=inicio,
            fim=fim,
        )
    ]
    if categoria_id is None:
        for transferencia in RepositorioTransferencias(sessao).filtradas(
            instituicao_id=instituicao_id, moeda=MOEDA_LANCAMENTOS, inicio=inicio, fim=fim
        ):
            linhas += [
                linha
                for linha in linhas_da_transferencia(transferencia)
                if (tipo is None or linha.tipo is tipo)
                and (instituicao_id is None or linha.instituicao_id == instituicao_id)
            ]
    # Mais recente primeiro (data, depois instante de criação); empate pela chave.
    linhas.sort(key=lambda x: x.chave)
    linhas.sort(key=lambda x: (x.data, x.criado_em), reverse=True)
    return PaginaLancamentos(linhas[deslocamento : deslocamento + limite], len(linhas))


# ------------------------------------------------------------- Resumos do mês


def _do_mes(
    sessao: Session, ano: int, mes: int, instituicao_id: int | None = None
) -> list[Lancamento]:
    validar_mes(ano, mes)
    return [
        Lancamento(
            data=registro.data,
            tipo=registro.tipo,
            valor=registro.valor,
            categoria_id=registro.categoria_id,
            categoria_nome=registro.categoria.nome if registro.categoria else None,
            instituicao_id=registro.instituicao_id,
        )
        for registro in RepositorioLancamentos(sessao).do_mes(ano, mes, instituicao_id)
    ]


def obter_resumo_mensal(
    sessao: Session, ano: int, mes: int, instituicao_id: int | None = None
) -> ResumoMensal:
    return resumo_mensal(_do_mes(sessao, ano, mes, instituicao_id), ano, mes)


def obter_totais_por_categoria(
    sessao: Session, ano: int, mes: int, instituicao_id: int | None = None
) -> list[TotalCategoria]:
    return totais_por_categoria(_do_mes(sessao, ano, mes, instituicao_id), ano, mes)


@dataclass(frozen=True)
class ResumoInstituicaoNomeado:
    instituicao: m.Instituicao
    resumo: ResumoInstituicao


def obter_resumo_por_instituicao(
    sessao: Session, ano: int, mes: int
) -> list[ResumoInstituicaoNomeado]:
    """Receitas, despesas, transferências (BRL) e saldo do mês por instituição, por nome."""
    validar_mes(ano, mes)
    inicio = date(ano, mes, 1)
    fim = primeiro_dia_do_proximo_mes(inicio) - timedelta(days=1)
    transferencias = [
        TransferenciaMes(t.data, t.origem_id, t.destino_id, t.valor)
        for t in RepositorioTransferencias(sessao).filtradas(
            moeda=MOEDA_LANCAMENTOS, inicio=inicio, fim=fim
        )
    ]
    resumos = resumo_por_instituicao(_do_mes(sessao, ano, mes), transferencias, ano, mes)
    nomeados = [
        ResumoInstituicaoNomeado(obter_instituicao(sessao, r.instituicao_id), r) for r in resumos
    ]
    return sorted(nomeados, key=lambda x: x.instituicao.nome.casefold())
