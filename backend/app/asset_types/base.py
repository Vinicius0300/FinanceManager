"""Contrato dos handlers de tipo de ativo.

Cada tipo de ativo é um handler isolado que declara:
- **identidade**: ``slug`` (gravado em ``ativos.tipo``), nome e descrição;
- **modo de posição**: ``cotas`` (quantidade × preço) ou ``montante`` (aportes/resgates
  em R$ com accrual);
- **provider**: nome da fonte de cotação no registry de ``app/providers``;
- **campos específicos**: schema que gera o formulário no front e valida os metadados;
- **transações aceitas** e regras extras de validação;
- **valor atual**: :meth:`HandlerCotado.avaliar` ou :meth:`HandlerMontante.avaliar`.

Para criar um tipo novo, herde de :class:`HandlerCotado` ou :class:`HandlerMontante`
em um arquivo próprio e registre-o em ``catalogo.py`` (ver ``docs/TIPOS_DE_ATIVO.md``).
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar

from app.domain.agenda import AGENDA_DIARIA, Agenda
from app.domain.enums import OrigemPreco, TipoIndicador, TipoTransacao
from app.domain.erros import DetalheCampo, OperacaoNaoPermitidaError, ValidacaoError
from app.domain.indicadores import Indicadores
from app.domain.montante import EstadoMontante, FatorAcumulado
from app.domain.numeros import dec, texto_decimal
from app.domain.posicao import EstadoPosicao
from app.domain.precos import SeriePrecos

Metadados = dict[str, str | int]
"""Metadados normalizados: decimais e datas como texto (JSON), inteiros como int."""


class TipoCampo(StrEnum):
    TEXTO = "texto"
    DECIMAL = "decimal"
    INTEIRO = "inteiro"
    DATA = "data"
    ESCOLHA = "escolha"


class ModoPosicao(StrEnum):
    COTAS = "cotas"
    MONTANTE = "montante"


@dataclass(frozen=True)
class Opcao:
    valor: str
    rotulo: str


@dataclass(frozen=True)
class CampoEspecifico:
    """Campo específico de um tipo de ativo (vira um campo de formulário no front)."""

    nome: str
    rotulo: str
    tipo: TipoCampo
    obrigatorio: bool = True
    ajuda: str | None = None
    opcoes: tuple[Opcao, ...] = ()
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    tamanho_maximo: int | None = None

    def para_schema(self) -> dict[str, Any]:
        """Representação JSON do campo (consumida pelo gerador de formulários)."""
        return {
            "nome": self.nome,
            "rotulo": self.rotulo,
            "tipo": self.tipo.value,
            "obrigatorio": self.obrigatorio,
            "ajuda": self.ajuda,
            "opcoes": [{"valor": o.valor, "rotulo": o.rotulo} for o in self.opcoes],
            "minimo": None if self.minimo is None else texto_decimal(self.minimo),
            "maximo": None if self.maximo is None else texto_decimal(self.maximo),
            "tamanho_maximo": self.tamanho_maximo,
        }

    def normalizar(self, bruto: object) -> str | int:
        """Converte e valida o valor; levanta ``ValueError`` com mensagem em pt-BR."""
        if self.tipo is TipoCampo.TEXTO:
            return self._texto(bruto)
        if self.tipo is TipoCampo.DECIMAL:
            return texto_decimal(self._no_intervalo(self._decimal(bruto)))
        if self.tipo is TipoCampo.INTEIRO:
            if isinstance(bruto, bool) or not isinstance(bruto, int):
                raise ValueError("Informe um número inteiro.")
            self._no_intervalo(dec(bruto))
            return bruto
        if self.tipo is TipoCampo.DATA:
            return self._data(bruto).isoformat()
        valores = [o.valor for o in self.opcoes]
        if bruto not in valores:
            raise ValueError(f"Opção inválida. Use uma de: {', '.join(valores)}.")
        return str(bruto)

    def _texto(self, bruto: object) -> str:
        if not isinstance(bruto, str):
            raise ValueError("Informe um texto.")
        texto = bruto.strip()
        if not texto:
            raise ValueError("Campo obrigatório.")
        if self.tamanho_maximo is not None and len(texto) > self.tamanho_maximo:
            raise ValueError(f"Use no máximo {self.tamanho_maximo} caracteres.")
        return texto

    @staticmethod
    def _decimal(bruto: object) -> Decimal:
        if isinstance(bruto, bool) or not isinstance(bruto, Decimal | int | str):
            raise ValueError("Informe um número (use ponto como separador decimal).")
        try:
            return dec(bruto)
        except ValueError as erro:
            raise ValueError("Informe um número (use ponto como separador decimal).") from erro

    def _no_intervalo(self, valor: Decimal) -> Decimal:
        if self.minimo is not None and valor < self.minimo:
            raise ValueError(f"O valor mínimo é {texto_decimal(self.minimo)}.")
        if self.maximo is not None and valor > self.maximo:
            raise ValueError(f"O valor máximo é {texto_decimal(self.maximo)}.")
        return valor

    @staticmethod
    def _data(bruto: object) -> date:
        if isinstance(bruto, date):
            return bruto
        if isinstance(bruto, str):
            try:
                return date.fromisoformat(bruto.strip())
            except ValueError as erro:
                raise ValueError("Data inválida. Use o formato AAAA-MM-DD.") from erro
        raise ValueError("Data inválida. Use o formato AAAA-MM-DD.")


@dataclass(frozen=True)
class Valoracao:
    """Valor atual de uma posição, na moeda do ativo, e de onde ele veio."""

    valor: Decimal
    preco_unitario: Decimal | None
    origem: OrigemPreco
    data_preco: date | None
    defasado: bool = False
    aviso: str | None = None


def ler_decimal(metadados: Mapping[str, object], nome: str) -> Decimal:
    valor = metadados[nome]
    if not isinstance(valor, str | int):
        raise TypeError(f"Metadado {nome} com tipo inesperado.")
    return dec(valor)


def ler_data(metadados: Mapping[str, object], nome: str) -> date:
    return date.fromisoformat(str(metadados[nome]))


class HandlerTipoAtivo(ABC):
    slug: ClassVar[str]
    nome: ClassVar[str]
    descricao: ClassVar[str]
    modo: ClassVar[ModoPosicao]
    moedas_aceitas: ClassVar[tuple[str, ...]]  # a primeira é a padrão
    provider: ClassVar[str | None] = None
    campos: ClassVar[tuple[CampoEspecifico, ...]] = ()
    tipos_transacao: ClassVar[frozenset[TipoTransacao]]
    aceita_taxas: ClassVar[bool] = True
    """``False``: compra/venda deste tipo não aceitam taxas (ex.: Tesouro Direto)."""
    agenda: ClassVar[Agenda] = AGENDA_DIARIA
    """Quando a atualização automática coleta a cotação (ver ``domain/agenda.py``)."""
    campos_identificacao: ClassVar[frozenset[str]] = frozenset()
    """Campos específicos que identificam o ativo na fonte de cotação (ex.: CNPJ do fundo).
    Alterá-los reinicia a coleta (apaga preços automáticos e baixa o histórico de novo)."""

    @property
    def moeda_padrao(self) -> str:
        return self.moedas_aceitas[0]

    def validar_moeda(self, moeda: str | None) -> str:
        escolhida = (moeda or self.moeda_padrao).strip().upper()
        if escolhida not in self.moedas_aceitas:
            mensagem = f"{self.nome} aceita apenas: {', '.join(self.moedas_aceitas)}."
            raise ValidacaoError(mensagem, [DetalheCampo("moeda", mensagem)])
        return escolhida

    def validar_metadados(self, dados: Mapping[str, object]) -> Metadados:
        """Valida contra o schema de campos + regras do tipo; devolve os metadados normalizados."""
        erros: list[DetalheCampo] = []
        normalizados: Metadados = {}
        conhecidos = {campo.nome for campo in self.campos}
        for nome in sorted(set(dados) - conhecidos):
            erros.append(DetalheCampo(nome, "Campo desconhecido para este tipo de ativo."))
        for campo in self.campos:
            bruto = dados.get(campo.nome)
            if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
                if campo.obrigatorio:
                    erros.append(DetalheCampo(campo.nome, "Campo obrigatório."))
                continue
            try:
                normalizados[campo.nome] = campo.normalizar(bruto)
            except ValueError as erro:
                erros.append(DetalheCampo(campo.nome, str(erro)))
        if not erros:
            erros.extend(self.regras_adicionais(normalizados))
        if erros:
            raise ValidacaoError(f"Dados inválidos para {self.nome}.", erros)
        return normalizados

    def regras_adicionais(self, metadados: Metadados) -> list[DetalheCampo]:
        """Regras que envolvem mais de um campo (sobrescreva quando precisar)."""
        return []

    def validar_transacao(self, metadados: Metadados, tipo: TipoTransacao, data: date) -> None:
        if tipo not in self.tipos_transacao:
            aceitas = ", ".join(sorted(t.value for t in self.tipos_transacao))
            raise OperacaoNaoPermitidaError(
                f"{self.nome} não aceita transação do tipo {tipo.value}. Aceita: {aceitas}."
            )

    def indicadores_necessarios(self, metadados: Metadados) -> frozenset[TipoIndicador]:
        """Indicadores que o cálculo do valor usa (para a atualização da Parte 3)."""
        return frozenset()

    def schema(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "nome": self.nome,
            "descricao": self.descricao,
            "modo": self.modo.value,
            "moeda_padrao": self.moeda_padrao,
            "moedas_aceitas": list(self.moedas_aceitas),
            "provider": self.provider,
            "tipos_transacao": sorted(t.value for t in self.tipos_transacao),
            "aceita_taxas": self.aceita_taxas,
            "campos": [campo.para_schema() for campo in self.campos],
        }


class HandlerCotado(HandlerTipoAtivo):
    """Ativo com cotação: valor = quantidade × último preço salvo."""

    modo = ModoPosicao.COTAS
    tipos_transacao: ClassVar[frozenset[TipoTransacao]] = frozenset(
        {TipoTransacao.COMPRA, TipoTransacao.VENDA, TipoTransacao.PROVENTO}
    )
    tolerancia_defasagem: ClassVar[timedelta] = timedelta(days=4)
    """Idade máxima do preço antes de marcar defasado (cobre fim de semana + feriado)."""

    def avaliar(self, estado: EstadoPosicao, precos: SeriePrecos, data_ref: date) -> Valoracao:
        ponto = precos.ultimo_ate(data_ref)
        if ponto is None:
            return Valoracao(
                valor=estado.moeda.custo,
                preco_unitario=estado.preco_medio,
                origem=OrigemPreco.CALCULADO,
                data_preco=None,
                defasado=True,
                aviso="Sem cotação registrada: usando o preço médio de compra.",
            )
        return Valoracao(
            valor=estado.quantidade * ponto.valor,
            preco_unitario=ponto.valor,
            origem=ponto.origem,
            data_preco=ponto.data,
            defasado=data_ref - ponto.data > self.tolerancia_defasagem,
        )


class HandlerMontante(HandlerTipoAtivo):
    """Investimento por montante (R$) com valor estimado por accrual (origem ``calculado``)."""

    modo = ModoPosicao.MONTANTE
    moedas_aceitas: ClassVar[tuple[str, ...]] = ("BRL",)
    tipos_transacao: ClassVar[frozenset[TipoTransacao]] = frozenset(
        {TipoTransacao.APORTE, TipoTransacao.RESGATE}
    )

    def referencia_indicadores(self, metadados: Metadados, data_ref: date) -> date:
        """Até que data o cálculo precisa de indicadores (usado no aviso de defasagem)."""
        return data_ref

    @abstractmethod
    def criar_fator(self, metadados: Metadados, indicadores: Indicadores) -> FatorAcumulado:
        """Fator de rendimento ``(inicio, fim) -> Decimal`` deste investimento."""

    def avaliar(self, estado: EstadoMontante, fator: FatorAcumulado, data_ref: date) -> Valoracao:
        return Valoracao(
            valor=estado.valor_em(data_ref, fator),
            preco_unitario=None,
            origem=OrigemPreco.CALCULADO,
            data_preco=data_ref,
        )
