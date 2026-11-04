"""Helper único de texto (``domain/textos.py``) e o uso dele nos services (bloco 2 do review)."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import TipoEvento, TipoLancamento, TipoMovimento
from app.domain.erros import ValidacaoError
from app.domain.textos import limpar_texto, texto_obrigatorio, texto_opcional
from app.services.caixa import NovoMovimentoManual, registrar_movimento_manual
from app.services.financeiro import NovoLancamento, criar_categoria, registrar_lancamento
from app.services.transacoes import NovoEvento, editar_evento, registrar_evento
from tests.fabricas import D, acao_br, compra, instituicao


def detalhes(erro: pytest.ExceptionInfo[ValidacaoError]) -> dict[str, str]:
    return {d.campo: d.mensagem for d in erro.value.detalhes}


# ---------------------------------------------------------------- domínio


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, None), ("", None), ("   ", None), ("\t\n ", None), (" ab ", "ab"), ("a b", "a b")],
)
def test_limpar_texto(valor: str | None, esperado: str | None) -> None:
    assert limpar_texto(valor) == esperado


def test_texto_opcional_vazio_vira_none_e_limpa_as_pontas() -> None:
    assert texto_opcional(None, "obs", 5) is None
    assert texto_opcional("     ", "obs", 5) is None
    assert texto_opcional("  abc  ", "obs", 5) == "abc"


def test_texto_opcional_conta_o_tamanho_sem_os_espacos_das_pontas() -> None:
    # "  abcde  " tem 9 caracteres, mas limpo tem 5: cabe no limite de 5.
    assert texto_opcional("  abcde  ", "obs", 5) == "abcde"
    with pytest.raises(ValidacaoError) as erro:
        texto_opcional("abcdef", "obs", 5)
    assert str(erro.value) == "Use no máximo 5 caracteres."
    assert detalhes(erro) == {"obs": "Use no máximo 5 caracteres."}


def test_texto_opcional_com_rotulo_prefixa_a_mensagem_principal() -> None:
    with pytest.raises(ValidacaoError) as erro:
        texto_opcional("abcdef", "simbolo", 5, "O símbolo")
    assert str(erro.value) == "O símbolo: Use no máximo 5 caracteres."
    assert detalhes(erro) == {"simbolo": "Use no máximo 5 caracteres."}


def test_texto_obrigatorio_mensagens() -> None:
    assert texto_obrigatorio(" Nome ", "nome", 10, "O nome") == "Nome"
    with pytest.raises(ValidacaoError) as erro:
        texto_obrigatorio("   ", "nome", 10, "O nome")
    assert str(erro.value) == "O nome é obrigatório."
    assert detalhes(erro) == {"nome": "Campo obrigatório."}
    with pytest.raises(ValidacaoError) as erro:
        texto_obrigatorio(None, "descricao", 10, mensagem_vazio="Informe a descrição.")
    assert str(erro.value) == "Informe a descrição."
    assert detalhes(erro) == {"descricao": "Informe a descrição."}
    with pytest.raises(ValidacaoError) as erro:
        texto_obrigatorio("", "nome", 10)
    assert detalhes(erro) == {"nome": "Campo obrigatório."}


# ---------------------------------------------------------------- services


def test_observacao_do_evento_so_com_espacos_vira_none(sessao: Session) -> None:
    # Bug do review: antes a observação "   " do evento era gravada como "" (e não None).
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "100", "10")
    evento = registrar_evento(
        sessao,
        NovoEvento(tst.id, TipoEvento.DESDOBRAMENTO, date(2025, 3, 2), 1, 2, observacao="   "),
    )
    assert evento.observacao is None
    editado = editar_evento(
        sessao,
        evento.id,
        NovoEvento(tst.id, TipoEvento.DESDOBRAMENTO, date(2025, 3, 2), 1, 2, observacao=" \t "),
    )
    assert editado.observacao is None


def test_observacao_do_evento_longa_e_recusada(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    compra(sessao, tst, rico, date(2025, 3, 1), "100", "10")
    with pytest.raises(ValidacaoError) as erro:
        registrar_evento(
            sessao,
            NovoEvento(
                tst.id, TipoEvento.DESDOBRAMENTO, date(2025, 3, 2), 1, 2, observacao="x" * 501
            ),
        )
    assert detalhes(erro) == {"observacao": "Use no máximo 500 caracteres."}


def test_observacao_da_transacao_so_com_espacos_vira_none(sessao: Session) -> None:
    rico, tst = instituicao(sessao), acao_br(sessao)
    vazia = compra(sessao, tst, rico, date(2025, 3, 1), "10", "10", observacao="   ").transacao
    assert vazia is not None
    assert vazia.observacao is None
    nota = compra(sessao, tst, rico, date(2025, 3, 1), "10", "10", observacao=" nota ").transacao
    assert nota is not None
    assert nota.observacao == "nota"


def test_descricao_do_movimento_e_observacao_do_lancamento_so_com_espacos(
    sessao: Session,
) -> None:
    rico = instituicao(sessao)
    movimento = registrar_movimento_manual(
        sessao,
        NovoMovimentoManual(rico.id, "BRL", TipoMovimento.DEPOSITO, date(2025, 3, 1), D(10), "  "),
    )
    assert movimento.descricao is None
    lancamento = registrar_lancamento(
        sessao,
        NovoLancamento(
            TipoLancamento.DESPESA, date(2025, 3, 1), " Feira ", D(10), observacao="   "
        ),
    )
    assert (lancamento.descricao, lancamento.observacao) == ("Feira", None)
    with pytest.raises(ValidacaoError) as erro:
        registrar_lancamento(
            sessao, NovoLancamento(TipoLancamento.DESPESA, date(2025, 3, 1), "   ", D(10))
        )
    assert detalhes(erro) == {"descricao": "Informe a descrição."}
    with pytest.raises(ValidacaoError) as erro:
        criar_categoria(sessao, "  ", TipoLancamento.DESPESA)
    assert detalhes(erro) == {"nome": "Informe o nome da categoria."}
