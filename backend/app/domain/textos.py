"""Limpeza e validação de textos digitados pelo usuário (regra única para todos os services).

Regra: espaços nas pontas são removidos; texto vazio ou só com espaços vira ``None`` nos campos
opcionais e é recusado nos obrigatórios; acima do tamanho máximo é recusado (nunca cortado).
"""

from app.domain.erros import DetalheCampo, ValidacaoError


def limpar_texto(valor: str | None) -> str | None:
    """Tira os espaços das pontas; ``None``, vazio ou só espaços viram ``None``."""
    if valor is None:
        return None
    texto = valor.strip()
    return texto or None


def _exigir_tamanho(texto: str, campo: str, tamanho: int, rotulo: str | None) -> None:
    if len(texto) > tamanho:
        mensagem = f"Use no máximo {tamanho} caracteres."
        principal = f"{rotulo}: {mensagem}" if rotulo else mensagem
        raise ValidacaoError(principal, [DetalheCampo(campo, mensagem)])


def texto_opcional(
    valor: str | None, campo: str, tamanho: int, rotulo: str | None = None
) -> str | None:
    """Texto opcional limpo (``None`` se vazio). ``rotulo`` prefixa a mensagem principal do erro
    de tamanho (ex.: "O símbolo: Use no máximo 30 caracteres.")."""
    texto = limpar_texto(valor)
    if texto is not None:
        _exigir_tamanho(texto, campo, tamanho, rotulo)
    return texto


def texto_obrigatorio(
    valor: str | None,
    campo: str,
    tamanho: int,
    rotulo: str | None = None,
    *,
    mensagem_vazio: str | None = None,
) -> str:
    """Texto obrigatório limpo. Vazio é recusado com ``mensagem_vazio`` (mesma mensagem no campo)
    ou, sem ela, com "<rotulo> é obrigatório." e "Campo obrigatório." no campo."""
    texto = limpar_texto(valor)
    if texto is None:
        if mensagem_vazio is not None:
            raise ValidacaoError(mensagem_vazio, [DetalheCampo(campo, mensagem_vazio)])
        principal = f"{rotulo} é obrigatório." if rotulo else "Campo obrigatório."
        raise ValidacaoError(principal, [DetalheCampo(campo, "Campo obrigatório.")])
    _exigir_tamanho(texto, campo, tamanho, rotulo)
    return texto
