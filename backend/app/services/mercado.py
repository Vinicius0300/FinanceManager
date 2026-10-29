"""Casos de uso de dados de mercado: registrar preços/indicadores e montá-los para cálculo.

O registro **automático** (providers e jobs) entra na Parte 3; aqui ficam o registro
manual e a leitura que alimenta os cálculos.
"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.enums import OrigemPreco, TipoIndicador
from app.domain.erros import ConflitoError, exigir
from app.domain.indicadores import NOMES_INDICADORES, Indicadores, PontoIndicador, SerieIndicador
from app.domain.moedas import MOEDA_BASE, validar_moeda
from app.domain.numeros import CASAS_CAMBIO, CASAS_PRECO, ZERO, exigir_casas
from app.domain.precos import PontoPreco, SeriePrecos
from app.domain.tempo import formatar_data
from app.repositories.mercado import RepositorioIndicadores, RepositorioPrecos
from app.repositories.modelos import Indicador, Preco
from app.services.cadastros import obter_ativo


def registrar_preco(
    sessao: Session,
    ativo_id: int,
    data_hora: datetime,
    valor: Decimal,
    origem: OrigemPreco,
    provider: str | None = None,
) -> Preco:
    ativo = obter_ativo(sessao, ativo_id)
    exigir(data_hora.tzinfo is not None, "data_hora", "Informe a data/hora com fuso horário.")
    exigir(valor > ZERO, "valor", "O preço deve ser maior que zero.")
    # Providers (Parte 3) devem arredondar a cotação antes de gravar (floats da fonte).
    exigir_casas(valor, CASAS_PRECO, "valor")
    exigir(
        origem is not OrigemPreco.AUTOMATICO or bool(provider),
        "provider",
        "Preço automático precisa informar o provider.",
    )
    repositorio = RepositorioPrecos(sessao)
    if repositorio.no_instante(ativo.id, data_hora) is not None:
        raise ConflitoError("Já existe um preço deste ativo nesse mesmo instante.")
    return repositorio.adicionar(
        Preco(
            ativo_id=ativo.id,
            data_hora=data_hora,
            valor=valor,
            moeda=ativo.moeda,
            origem=origem,
            provider=provider,
        )
    )


def registrar_indicador(
    sessao: Session,
    tipo: TipoIndicador,
    data: date,
    valor: Decimal,
    moeda: str = MOEDA_BASE,
    fonte: str | None = None,
) -> Indicador:
    moeda = validar_moeda(moeda)
    if tipo is TipoIndicador.CAMBIO:
        exigir(moeda != MOEDA_BASE, "moeda", "Câmbio deve ser de uma moeda estrangeira.")
        exigir(valor > ZERO, "valor", "O câmbio deve ser maior que zero.")
        exigir_casas(valor, CASAS_CAMBIO, "valor")
    else:
        exigir(moeda == MOEDA_BASE, "moeda", "Selic, CDI e IPCA são indicadores em BRL.")
    if tipo in (TipoIndicador.SELIC, TipoIndicador.CDI):
        exigir(valor >= ZERO, "valor", "A taxa não pode ser negativa.")
    if tipo is TipoIndicador.IPCA:
        exigir(data.day == 1, "data", "O IPCA é mensal: use o dia 1º do mês de referência.")
    repositorio = RepositorioIndicadores(sessao)
    if repositorio.na_data(tipo, moeda, data) is not None:
        raise ConflitoError(
            f"Já existe {NOMES_INDICADORES[tipo]} registrado para {formatar_data(data)}."
        )
    return repositorio.adicionar(
        Indicador(tipo=tipo, moeda=moeda, data=data, valor=valor, fonte=fonte)
    )


def carregar_indicadores(sessao: Session) -> Indicadores:
    pontos: dict[tuple[TipoIndicador, str], list[PontoIndicador]] = defaultdict(list)
    for registro in RepositorioIndicadores(sessao).listar():
        pontos[(registro.tipo, registro.moeda)].append(
            PontoIndicador(registro.data, registro.valor)
        )
    return Indicadores(
        SerieIndicador(tipo, lista, moeda) for (tipo, moeda), lista in pontos.items()
    )


def carregar_precos(sessao: Session, ativo_id: int) -> SeriePrecos:
    return SeriePrecos(
        PontoPreco(p.data_hora, p.valor, p.origem)
        for p in RepositorioPrecos(sessao).do_ativo(ativo_id)
    )
