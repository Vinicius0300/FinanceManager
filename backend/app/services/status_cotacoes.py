"""Status da última atualização de cada ativo (para a tela e para a API).

- **Cotados:** último preço gravado (data/hora, valor, origem e provider), se está
  defasado pela tolerância do tipo (4 dias; cripto 1) e o estado da coleta (última
  tentativa, último sucesso e último erro).
- **Por montante** (renda fixa, poupança): valor sempre ``calculado``; defasado só quando
  falta o indicador recente usado no cálculo.
- **Situação** (chip e painel da barra superior): ``domain/situacao_cotacao.py``; cotado sem
  provider vira ``manual`` (o app não busca o preço sozinho).
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.asset_types.base import HandlerCotado, HandlerMontante
from app.asset_types.catalogo import REGISTRO_PADRAO
from app.asset_types.registry import RegistroTiposAtivo
from app.domain.enums import OrigemPreco
from app.domain.indicadores import aviso_indicador_defasado
from app.domain.situacao_cotacao import SituacaoCotacao, classificar_situacao
from app.repositories import modelos as m
from app.repositories.mercado import RepositorioEstadosColeta, RepositorioPrecos
from app.services.cadastros import listar_ativos, obter_ativo
from app.services.coleta import chave_ativo
from app.services.mercado import carregar_indicadores

AVISO_MANUAL = "Sem fonte automática: o preço é informado à mão."


@dataclass(frozen=True)
class StatusAtivo:
    ativo_id: int
    nome: str
    simbolo: str | None
    tipo: str
    moeda: str
    provider: str | None
    origem: OrigemPreco | None
    data: date | None
    data_hora: datetime | None
    valor: Decimal | None
    provider_preco: str | None
    defasado: bool
    aviso: str | None
    ultima_tentativa: datetime | None
    ultimo_sucesso: datetime | None
    ultimo_erro: str | None
    situacao: SituacaoCotacao


def _status(
    sessao: Session,
    ativo: m.Ativo,
    hoje: date,
    estados: dict[int, m.EstadoColeta],
    registro: RegistroTiposAtivo,
) -> StatusAtivo:
    item = _sem_situacao(sessao, ativo, hoje, estados, registro)
    handler = registro.obter(ativo.tipo)
    situacao = classificar_situacao(
        ultimo_erro=item.ultimo_erro,
        sem_fonte_automatica=isinstance(handler, HandlerCotado) and not ativo.provider,
        defasado=item.defasado,
    )
    if situacao is SituacaoCotacao.MANUAL:
        # ``defasado`` continua dizendo a idade do preço; o aviso explica por que não conta.
        return replace(item, situacao=situacao, aviso=AVISO_MANUAL)
    return replace(item, situacao=situacao)


def _sem_situacao(
    sessao: Session,
    ativo: m.Ativo,
    hoje: date,
    estados: dict[int, m.EstadoColeta],
    registro: RegistroTiposAtivo,
) -> StatusAtivo:
    handler = registro.obter(ativo.tipo)
    estado = estados.get(ativo.id)
    base = StatusAtivo(
        ativo_id=ativo.id,
        nome=ativo.nome,
        simbolo=ativo.simbolo,
        tipo=ativo.tipo,
        moeda=ativo.moeda,
        provider=ativo.provider,
        origem=None,
        data=None,
        data_hora=None,
        valor=None,
        provider_preco=None,
        defasado=False,
        aviso=None,
        ultima_tentativa=estado.ultima_tentativa if estado else None,
        ultimo_sucesso=estado.ultimo_sucesso if estado else None,
        ultimo_erro=estado.ultimo_erro if estado else None,
        situacao=SituacaoCotacao.EM_DIA,  # definida em ``_status``
    )
    if isinstance(handler, HandlerMontante):
        indicadores = carregar_indicadores(sessao)
        referencia = handler.referencia_indicadores(ativo.metadados, hoje)
        avisos = [
            aviso
            for tipo in sorted(handler.indicadores_necessarios(ativo.metadados))
            if (aviso := aviso_indicador_defasado(indicadores.serie(tipo), referencia))
        ]
        return replace(
            base,
            origem=OrigemPreco.CALCULADO,
            data=hoje,
            defasado=bool(avisos),
            aviso=" ".join(avisos) or None,
        )
    ultimos = RepositorioPrecos(sessao).ultimos(ativo.id, 1)
    if not ultimos:
        return replace(
            base,
            defasado=True,
            aviso="Sem cotação registrada: o valor usa o preço médio de compra.",
        )
    preco = ultimos[0]
    tolerancia = handler.tolerancia_defasagem if isinstance(handler, HandlerCotado) else None
    defasado = tolerancia is not None and hoje - preco.data > tolerancia
    return replace(
        base,
        origem=preco.origem,
        data=preco.data,
        data_hora=preco.data_hora,
        valor=preco.valor,
        provider_preco=preco.provider,
        defasado=defasado,
        aviso="Cotação defasada: usando o último preço salvo." if defasado else None,
    )


def status_ativos(
    sessao: Session, hoje: date, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> list[StatusAtivo]:
    estados = RepositorioEstadosColeta(sessao).de_ativos()
    return [_status(sessao, a, hoje, estados, registro) for a in listar_ativos(sessao)]


def status_ativo(
    sessao: Session, ativo_id: int, hoje: date, registro: RegistroTiposAtivo = REGISTRO_PADRAO
) -> StatusAtivo:
    ativo = obter_ativo(sessao, ativo_id)
    estado = RepositorioEstadosColeta(sessao).obter(chave_ativo(ativo.id))
    return _status(sessao, ativo, hoje, {ativo.id: estado} if estado else {}, registro)
