"""Checagem do contrato: ``docs/openapi.json`` precisa ser igual ao gerado pelo app.

Se este teste falhar, a API mudou sem regenerar o contrato: rode ``npm run contrato``
(na raiz) e commite ``docs/openapi.json`` e ``apps/web/src/api/schema.ts``. O
``npm run contrato:verificar`` continua cobrindo o ``schema.ts`` (precisa do Node).
"""

from pathlib import Path

from app.core.contrato import texto_openapi

ARQUIVO = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def test_openapi_commitado_esta_atualizado() -> None:
    commitado = ARQUIVO.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert commitado == texto_openapi(), (
        "docs/openapi.json desatualizado: rode 'npm run contrato' na raiz e commite o resultado."
    )


def test_contrato_tem_as_rotas_da_parte_3() -> None:
    import json

    caminhos = set(json.loads(texto_openapi())["paths"])
    esperados = {
        "/api/instituicoes",
        "/api/contas",
        "/api/movimentos",
        "/api/instituicoes/{instituicao_id}/extrato",
        "/api/tipos-ativo",
        "/api/ativos",
        "/api/transacoes",
        "/api/eventos-corporativos",
        "/api/ativos/{ativo_id}/precos",
        "/api/cotacoes/status",
        "/api/cotacoes/atualizar",
        "/api/indicadores",
        "/api/portfolio/resumo",
        "/api/portfolio/posicoes",
        "/api/portfolio/alocacao",
        "/api/portfolio/evolucao",
        "/api/portfolio/maiores",
        "/api/portfolio/variacao-dia",
        "/api/portfolio/rentabilidade",
        "/api/lancamentos",
        "/api/categorias",
        "/api/resumo-mensal",
        "/api/configuracoes",
        "/api/backups",
        "/api/backups/restaurar",
        "/api/eventos",
    }
    assert esperados <= caminhos
