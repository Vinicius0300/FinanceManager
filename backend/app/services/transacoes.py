"""Casos de uso de transações e eventos corporativos.

Registrar uma transação:
1. valida ativo, instituição, tipo aceito pelo handler, campos e câmbio;
2. **reprocessa a posição** com a operação incluída (pega venda maior que a posição,
   resgate maior que o saldo e efeitos retroativos);
3. calcula o movimento automático da conta corrente da instituição. Se uma compra/aporte
   exceder o saldo, devolve um **aviso** sem gravar nada; com ``aceitar_ajuste=True``,
   grava a transação e um ``ajuste_saldo`` (depósito não informado) pela diferença.

Excluir uma transação ou evento reprocessa o histórico sem ela e recusa se algo ficar
inválido (ex.: excluir uma compra que sustentava uma venda posterior).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.asset_types.base import HandlerCotado, HandlerMontante
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.conta_corrente import (
    MENSAGEM_SALDO_INSUFICIENTE,
    LancamentoCaixa,
    deficit,
    movimento_da_transacao,
    valor_com_sinal,
)
from app.domain.enums import SubtipoProvento, TipoEvento, TipoMovimento, TipoTransacao
from app.domain.erros import (
    ConflitoError,
    DominioError,
    NaoEncontradoError,
    OperacaoNaoPermitidaError,
    PosicaoInsuficienteError,
    SaldoInsuficienteError,
    exigir,
)
from app.domain.numeros import (
    CASAS_MOEDA,
    CASAS_PRECO,
    CASAS_QUANTIDADE,
    ZERO,
    arredondar_moeda,
    exigir_casas,
    formatar_numero,
)
from app.domain.posicao import validar_proporcao_evento
from app.domain.tempo import formatar_data
from app.repositories import modelos as m
from app.repositories.contas import RepositorioMovimentos
from app.repositories.transacoes import RepositorioEventos, RepositorioTransacoes
from app.services.cadastros import handler_do_ativo, obter_ativo, obter_instituicao
from app.services.caixa import (
    DESCRICAO_AJUSTE,
    lancamentos,
    movimentos_da_conta,
    obter_conta,
    obter_ou_criar_conta,
)
from app.services.mercado import carregar_indicadores
from app.services.posicoes import (
    houve_compra_ate,
    operacao_cotas,
    reprocessar_ativo,
    resolver_cambio,
)

TAMANHO_OBSERVACAO = 500
TIPOS_COM_VALOR = frozenset({TipoTransacao.APORTE, TipoTransacao.RESGATE, TipoTransacao.PROVENTO})


@dataclass(frozen=True)
class NovaTransacao:
    ativo_id: int
    instituicao_id: int
    tipo: TipoTransacao
    data: date
    quantidade: Decimal | None = None  # compra/venda
    preco_unitario: Decimal | None = None  # compra/venda, na moeda do ativo
    valor: Decimal | None = None  # aporte/resgate em R$; provento líquido na moeda do ativo
    taxas: Decimal = ZERO
    cambio: Decimal | None = None  # BRL por unidade; buscado em indicadores se omitido
    subtipo_provento: SubtipoProvento | None = None
    imposto_retido: Decimal = ZERO
    observacao: str | None = None


@dataclass(frozen=True)
class AvisoSaldoInsuficiente:
    mensagem: str
    instituicao_id: int
    moeda: str
    data: date
    valor_faltante: Decimal  # valor do ajuste que será criado se o usuário continuar


@dataclass(frozen=True)
class ResultadoTransacao:
    transacao: m.Transacao | None
    aviso: AvisoSaldoInsuficiente | None = None
    ajuste: m.MovimentoConta | None = None

    @property
    def gravada(self) -> bool:
        return self.transacao is not None


def _validar_campos(dados: NovaTransacao) -> None:
    if dados.tipo in TIPOS_COM_VALOR:
        exigir(dados.valor is not None, "valor", "Informe o valor.")
        exigir(
            dados.quantidade is None and dados.preco_unitario is None,
            "quantidade",
            "Aporte, resgate e provento são informados só pelo valor.",
        )
    else:
        exigir(dados.quantidade is not None, "quantidade", "Informe a quantidade.")
        exigir(dados.preco_unitario is not None, "preco_unitario", "Informe o preço unitário.")
        exigir(
            dados.valor is None, "valor", "Compra e venda são informadas por quantidade e preço."
        )
    if dados.tipo is TipoTransacao.PROVENTO:
        exigir(
            dados.subtipo_provento is not None,
            "subtipo_provento",
            "Informe o tipo do provento (dividendo, JCP, rendimento ou outro).",
        )
    else:
        exigir(
            dados.subtipo_provento is None,
            "subtipo_provento",
            "Tipo de provento só se aplica a proventos.",
        )
        exigir(
            dados.imposto_retido == ZERO,
            "imposto_retido",
            "Imposto retido só se aplica a proventos.",
        )
    if dados.tipo in (TipoTransacao.APORTE, TipoTransacao.RESGATE):
        exigir(dados.taxas == ZERO, "taxas", "Aporte e resgate não aceitam taxas.")
    if dados.tipo is TipoTransacao.PROVENTO:
        exigir(dados.taxas == ZERO, "taxas", "Proventos não aceitam taxas.")
    observacao = dados.observacao
    exigir(
        observacao is None or len(observacao.strip()) <= TAMANHO_OBSERVACAO,
        "observacao",
        f"Use no máximo {TAMANHO_OBSERVACAO} caracteres.",
    )
    exigir_casas(dados.quantidade, CASAS_QUANTIDADE, "quantidade")
    exigir_casas(dados.preco_unitario, CASAS_PRECO, "preco_unitario")
    exigir_casas(dados.valor, CASAS_MOEDA, "valor")
    exigir_casas(dados.taxas, CASAS_MOEDA, "taxas")
    exigir_casas(dados.imposto_retido, CASAS_MOEDA, "imposto_retido")


def _sem_dominio(acao: str, erro: DominioError) -> OperacaoNaoPermitidaError:
    return OperacaoNaoPermitidaError(f"{acao}: {erro.mensagem}")


@dataclass(frozen=True)
class _Simulacao:
    """Transação validada (ainda não gravada) e o efeito dela no caixa."""

    transacao: m.Transacao
    tipo_movimento: TipoMovimento
    valor_movimento: Decimal
    faltante: Decimal


def _simular(
    sessao: Session,
    dados: NovaTransacao,
    registro: RegistroTiposAtivo,
    substituida: m.Transacao | None = None,
) -> _Simulacao:
    """Valida ``dados`` reprocessando o ativo (sem ``substituida``, na edição) e calcula o
    movimento de caixa e quanto faltaria de saldo. Não grava nada."""
    ativo = obter_ativo(sessao, dados.ativo_id)
    obter_instituicao(sessao, dados.instituicao_id)
    handler = handler_do_ativo(ativo, registro)
    handler.validar_transacao(ativo.metadados, dados.tipo, dados.data)
    _validar_campos(dados)
    exigir(
        handler.aceita_taxas or dados.taxas == ZERO, "taxas", f"{handler.nome} não aceita taxas."
    )
    indicadores = carregar_indicadores(sessao)
    observacao = dados.observacao.strip() if dados.observacao and dados.observacao.strip() else None
    ignorar = substituida.id if substituida is not None else None

    nova = m.Transacao(
        id=ignorar,  # na edição mantém a ordem original entre as operações do mesmo dia
        ativo_id=ativo.id,
        instituicao_id=dados.instituicao_id,
        tipo=dados.tipo,
        data=dados.data,
        quantidade=dados.quantidade,
        preco_unitario=dados.preco_unitario,
        valor=dados.valor,
        taxas=dados.taxas,
        moeda=ativo.moeda,
        cambio=resolver_cambio(dados.cambio, ativo.moeda, dados.data, indicadores),
        subtipo_provento=dados.subtipo_provento,
        imposto_retido=dados.imposto_retido,
        observacao=observacao,
    )
    repositorio = RepositorioTransacoes(sessao)
    outras = [t for t in repositorio.do_ativo(ativo.id) if ignorar is None or t.id != ignorar]
    da_posicao = [t for t in outras if t.instituicao_id == dados.instituicao_id]
    if isinstance(handler, HandlerCotado):
        operacao_cotas(nova)  # valida números (quantidade > 0, taxas ≤ venda...)
        if dados.tipo is TipoTransacao.PROVENTO and not houve_compra_ate(da_posicao, dados.data):
            raise OperacaoNaoPermitidaError(
                "Não há compra deste ativo nesta instituição até "
                f"{formatar_data(dados.data)} para receber o provento."
            )
    eventos = list(RepositorioEventos(sessao).do_ativo(ativo.id))
    reprocessar_ativo(ativo, handler, [*outras, nova], eventos, indicadores)

    tipo_movimento, valor_movimento = movimento_da_transacao(
        dados.tipo,
        quantidade=dados.quantidade,
        preco_unitario=dados.preco_unitario,
        taxas=dados.taxas,
        valor=dados.valor,
    )
    conta = obter_conta(sessao, dados.instituicao_id, ativo.moeda)
    existentes = (
        lancamentos(
            x
            for x in movimentos_da_conta(sessao, conta.id)
            if ignorar is None or x.transacao_id != ignorar
        )
        if conta
        else []
    )
    novo_lancamento = LancamentoCaixa(dados.data, valor_com_sinal(tipo_movimento, valor_movimento))
    faltante = deficit([*existentes, novo_lancamento], dados.data)
    return _Simulacao(nova, tipo_movimento, valor_movimento, faltante)


def _aviso(dados: NovaTransacao, moeda: str, faltante: Decimal) -> ResultadoTransacao:
    return ResultadoTransacao(
        transacao=None,
        aviso=AvisoSaldoInsuficiente(
            mensagem=MENSAGEM_SALDO_INSUFICIENTE,
            instituicao_id=dados.instituicao_id,
            moeda=moeda,
            data=dados.data,
            valor_faltante=faltante,
        ),
    )


def _gravar_movimentos(
    sessao: Session, transacao: m.Transacao, simulacao: _Simulacao
) -> m.MovimentoConta | None:
    """Cria o movimento automático da transação e, se faltar saldo, o ajuste."""
    conta = obter_ou_criar_conta(sessao, transacao.instituicao_id, transacao.moeda)
    movimentos = RepositorioMovimentos(sessao)
    if simulacao.valor_movimento > ZERO:  # compra a preço zero sem taxas não movimenta
        movimentos.adicionar(
            m.MovimentoConta(
                conta_id=conta.id,
                transacao_id=transacao.id,
                tipo=simulacao.tipo_movimento,
                data=transacao.data,
                valor=simulacao.valor_movimento,
            )
        )
    if simulacao.faltante <= ZERO:
        return None
    return movimentos.adicionar(
        m.MovimentoConta(
            conta_id=conta.id,
            transacao_id=transacao.id,
            tipo=TipoMovimento.AJUSTE_SALDO,
            data=transacao.data,
            valor=simulacao.faltante,
            descricao=DESCRICAO_AJUSTE,
        )
    )


def registrar_transacao(
    sessao: Session,
    dados: NovaTransacao,
    *,
    aceitar_ajuste: bool = False,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> ResultadoTransacao:
    simulacao = _simular(sessao, dados, registro)
    if simulacao.faltante > ZERO and not aceitar_ajuste:
        return _aviso(dados, simulacao.transacao.moeda, simulacao.faltante)
    transacao = RepositorioTransacoes(sessao).adicionar(simulacao.transacao)
    ajuste = _gravar_movimentos(sessao, transacao, simulacao)
    return ResultadoTransacao(transacao=transacao, ajuste=ajuste)


CAMPOS_EDITAVEIS = (
    "instituicao_id",
    "tipo",
    "data",
    "quantidade",
    "preco_unitario",
    "valor",
    "taxas",
    "cambio",
    "subtipo_provento",
    "imposto_retido",
    "observacao",
)


def editar_transacao(
    sessao: Session,
    transacao_id: int,
    dados: NovaTransacao,
    *,
    aceitar_ajuste: bool = False,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> ResultadoTransacao:
    """Substitui a transação pelos novos dados e reprocessa a posição.

    Recusa se algo ficar inválido (mesma regra da exclusão) e passa pelo aviso de saldo
    insuficiente como um registro novo. O ativo não muda (para isso, exclua e registre
    de novo). Os movimentos automáticos e o ajuste de saldo antigos são refeitos.
    """
    original = obter_transacao(sessao, transacao_id)
    exigir(
        dados.ativo_id == original.ativo_id,
        "ativo_id",
        "O ativo de uma transação não pode ser trocado: exclua e registre de novo.",
    )
    try:
        simulacao = _simular(sessao, dados, registro, substituida=original)
    except PosicaoInsuficienteError as erro:
        raise _sem_dominio("Não é possível alterar esta transação", erro) from erro
    if simulacao.faltante > ZERO and not aceitar_ajuste:
        return _aviso(dados, simulacao.transacao.moeda, simulacao.faltante)
    conta_antiga = obter_conta(sessao, original.instituicao_id, original.moeda)
    if conta_antiga is not None and original.instituicao_id != dados.instituicao_id:
        restantes = [
            x for x in movimentos_da_conta(sessao, conta_antiga.id) if x.transacao_id != original.id
        ]
        falta = deficit(lancamentos(restantes), original.data)
        if falta > ZERO:
            raise SaldoInsuficienteError(
                "Mudar a instituição desta transação deixaria a conta corrente anterior "
                f"negativa em R$ {formatar_numero(arredondar_moeda(falta))} a partir de "
                f"{formatar_data(original.data)}."
            )
    movimentos = RepositorioMovimentos(sessao)
    for movimento in movimentos.da_transacao(original.id):
        movimentos.remover(movimento)
    sessao.expire(original, ["movimentos"])
    for campo in CAMPOS_EDITAVEIS:
        setattr(original, campo, getattr(simulacao.transacao, campo))
    sessao.flush()
    ajuste = _gravar_movimentos(sessao, original, simulacao)
    return ResultadoTransacao(transacao=original, ajuste=ajuste)


def obter_transacao(sessao: Session, transacao_id: int) -> m.Transacao:
    transacao = RepositorioTransacoes(sessao).obter(transacao_id)
    if transacao is None:
        raise NaoEncontradoError(f"Transação {transacao_id} não encontrada.")
    return transacao


def excluir_transacao(
    sessao: Session, transacao_id: int, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> None:
    """Exclui a transação e seus movimentos automáticos (inclusive o ajuste de saldo)."""
    transacao = obter_transacao(sessao, transacao_id)
    ativo = obter_ativo(sessao, transacao.ativo_id)
    handler = handler_do_ativo(ativo, registro)
    restantes = [
        t for t in RepositorioTransacoes(sessao).do_ativo(ativo.id) if t.id != transacao.id
    ]
    eventos = list(RepositorioEventos(sessao).do_ativo(ativo.id))
    try:
        reprocessar_ativo(ativo, handler, restantes, eventos, carregar_indicadores(sessao))
    except DominioError as erro:
        raise _sem_dominio("Não é possível excluir esta transação", erro) from erro

    conta = obter_conta(sessao, transacao.instituicao_id, transacao.moeda)
    if conta is not None:
        outros = [
            x for x in movimentos_da_conta(sessao, conta.id) if x.transacao_id != transacao.id
        ]
        falta = deficit(lancamentos(outros), transacao.data)
        if falta > ZERO:
            raise SaldoInsuficienteError(
                "Excluir esta transação deixaria a conta corrente negativa em "
                f"R$ {formatar_numero(arredondar_moeda(falta))} a partir de "
                f"{formatar_data(transacao.data)}."
            )
    RepositorioTransacoes(sessao).remover(transacao)


@dataclass(frozen=True)
class NovoEvento:
    ativo_id: int
    tipo: TipoEvento
    data: date  # data "ex"
    proporcao_de: int
    proporcao_para: int
    custo_unitario: Decimal = ZERO  # só bonificação (moeda do ativo)
    cambio: Decimal | None = None  # BRL por unidade; buscado em indicadores se omitido
    observacao: str | None = None


def _preparar_evento(
    sessao: Session,
    dados: NovoEvento,
    registro: RegistroTiposAtivo,
    substituido: m.EventoCorporativo | None = None,
) -> m.EventoCorporativo:
    """Valida o evento e reprocessa o ativo com ele (sem ``substituido``). Não grava."""
    ativo = obter_ativo(sessao, dados.ativo_id)
    handler = handler_do_ativo(ativo, registro)
    if isinstance(handler, HandlerMontante):
        raise OperacaoNaoPermitidaError(f"{handler.nome} não tem eventos corporativos.")
    validar_proporcao_evento(
        dados.tipo, dados.proporcao_de, dados.proporcao_para, dados.custo_unitario
    )
    exigir_casas(dados.custo_unitario, CASAS_PRECO, "custo_unitario")
    indicadores = carregar_indicadores(sessao)
    cambio = resolver_cambio(
        dados.cambio,
        ativo.moeda,
        dados.data,
        indicadores,
        buscar=dados.custo_unitario > ZERO,
    )
    exigir(
        dados.observacao is None or len(dados.observacao.strip()) <= TAMANHO_OBSERVACAO,
        "observacao",
        f"Use no máximo {TAMANHO_OBSERVACAO} caracteres.",
    )
    ignorar = substituido.id if substituido is not None else None
    outros = [
        e
        for e in RepositorioEventos(sessao).do_ativo(ativo.id)
        if ignorar is None or e.id != ignorar
    ]
    if any(e.data == dados.data and e.tipo is dados.tipo for e in outros):
        raise ConflitoError(
            f"Já existe {dados.tipo.value} deste ativo em {formatar_data(dados.data)}."
        )
    novo = m.EventoCorporativo(
        id=ignorar,
        ativo_id=ativo.id,
        tipo=dados.tipo,
        data=dados.data,
        proporcao_de=dados.proporcao_de,
        proporcao_para=dados.proporcao_para,
        custo_unitario=dados.custo_unitario,
        cambio=cambio,
        observacao=dados.observacao.strip() if dados.observacao else None,
    )
    transacoes = list(RepositorioTransacoes(sessao).do_ativo(ativo.id))
    reprocessar_ativo(ativo, handler, transacoes, [*outros, novo], indicadores)
    return novo


def registrar_evento(
    sessao: Session, dados: NovoEvento, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> m.EventoCorporativo:
    """Registra desdobramento, grupamento ou bonificação (vale para todas as instituições).

    O câmbio fica gravado no evento (como nas transações), para o custo em BRL da
    bonificação não mudar se os indicadores forem alterados depois. Só é buscado quando
    importa: bonificação com custo atribuído em ativo estrangeiro.
    """
    return RepositorioEventos(sessao).adicionar(_preparar_evento(sessao, dados, registro))


def obter_evento(sessao: Session, evento_id: int) -> m.EventoCorporativo:
    evento = RepositorioEventos(sessao).obter(evento_id)
    if evento is None:
        raise NaoEncontradoError(f"Evento corporativo {evento_id} não encontrado.")
    return evento


def editar_evento(
    sessao: Session,
    evento_id: int,
    dados: NovoEvento,
    registro: RegistroTiposAtivo = REGISTRO_PADRAO,
) -> m.EventoCorporativo:
    """Substitui o evento e reprocessa o ativo; recusa se alguma posição ficar inválida."""
    original = obter_evento(sessao, evento_id)
    exigir(
        dados.ativo_id == original.ativo_id,
        "ativo_id",
        "O ativo de um evento não pode ser trocado: exclua e registre de novo.",
    )
    try:
        novo = _preparar_evento(sessao, dados, registro, substituido=original)
    except PosicaoInsuficienteError as erro:
        raise _sem_dominio("Não é possível alterar este evento", erro) from erro
    for campo in (
        "tipo",
        "data",
        "proporcao_de",
        "proporcao_para",
        "custo_unitario",
        "cambio",
        "observacao",
    ):
        setattr(original, campo, getattr(novo, campo))
    sessao.flush()
    return original


def excluir_evento(
    sessao: Session, evento_id: int, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> None:
    repositorio = RepositorioEventos(sessao)
    evento = obter_evento(sessao, evento_id)
    ativo = obter_ativo(sessao, evento.ativo_id)
    restantes = [e for e in repositorio.do_ativo(ativo.id) if e.id != evento.id]
    transacoes = list(RepositorioTransacoes(sessao).do_ativo(ativo.id))
    try:
        reprocessar_ativo(
            ativo,
            handler_do_ativo(ativo, registro),
            transacoes,
            restantes,
            carregar_indicadores(sessao),
        )
    except DominioError as erro:
        raise _sem_dominio("Não é possível excluir este evento", erro) from erro
    repositorio.remover(evento)


@dataclass(frozen=True)
class PaginaTransacoes:
    itens: Sequence[m.Transacao]
    total: int


def listar_transacoes(
    sessao: Session,
    *,
    ativo_id: int | None = None,
    instituicao_id: int | None = None,
    tipo: TipoTransacao | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = 50,
    deslocamento: int = 0,
) -> PaginaTransacoes:
    itens, total = RepositorioTransacoes(sessao).pagina(
        ativo_id=ativo_id,
        instituicao_id=instituicao_id,
        tipo=tipo,
        inicio=inicio,
        fim=fim,
        limite=limite,
        deslocamento=deslocamento,
    )
    return PaginaTransacoes(itens, total)


def listar_eventos(sessao: Session, ativo_id: int | None = None) -> Sequence[m.EventoCorporativo]:
    repositorio = RepositorioEventos(sessao)
    if ativo_id is None:
        return repositorio.listar()
    return list(reversed(repositorio.do_ativo(ativo_id)))
