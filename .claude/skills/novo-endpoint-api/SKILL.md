---
name: novo-endpoint-api
description: Cria ou modifica endpoints REST do backend FastAPI seguindo o padrão do projeto (schemas Pydantic v2, auth por token, erros em pt-BR, paginação, camadas api/services/repositories) e dispara a regeneração do contrato OpenAPI e do cliente TypeScript. Use sempre que o usuário pedir uma nova rota, novo recurso da API, novo filtro, novo campo de resposta ou ajuste de validação.
---

# Novo endpoint de API

## Princípios
- `api/` só valida entrada, chama `services/` e serializa a saída. Regra de negócio vive em `services/`/`domain/`; acesso ao banco, em `repositories/` (sem regra de negócio).
- Toda rota exige o token de sessão, **exceto `/health`**. Use a dependência de autenticação já existente; não crie outro mecanismo.

## Passos
1. **Schemas Pydantic v2** de entrada e saída, com validações e `Decimal` para dinheiro (serialização como string, sem perda de precisão). Nomeie campos no padrão do domínio já existente.
2. **Rota** com `response_model`, tags, `summary` e descrição úteis (alimentam a doc `/docs` e o cliente gerado). Use paginação (`limit`/`offset` ou cursor, conforme o padrão já adotado) onde a lista puder crescer.
3. **Erros padronizados em pt-BR:** use o formato de erro comum do projeto (código + mensagem legível). Não vaze stack trace nem detalhes internos. Códigos HTTP corretos (404 inexistente, 409 conflito, 422 validação).
4. **Service/repository:** adicione a lógica na camada certa. Se precisar de coluna nova, use `nova-migracao-alembic`.
5. **Tempo real:** se o evento interessa à UI (preço atualizado, erro de provider, fim de ciclo), publique no stream de eventos já existente (SSE via fetch streaming com `Authorization`, porque `EventSource` nativo não envia headers).
6. **Testes** com `TestClient`/`httpx`: sucesso, sem token (401/403), validação inválida, não encontrado, paginação e erros em pt-BR. Banco de teste isolado (SQLite temporário), sem internet.
7. **Contrato:** rode a skill `contrato-openapi` para regenerar `docs/openapi.json` e o cliente TS. Não termine a tarefa sem isso.
8. **Documente** o endpoint em `docs/CONTEXTO.md` se criar um recurso novo; atualize o roteiro de validação (ex.: testar pelo `/docs`).

## Checklist rápido
- [ ] Token exigido (exceto `/health`)
- [ ] Schemas v2, `Decimal` como string
- [ ] Erros pt-BR padronizados
- [ ] Testes (inclui falta de token)
- [ ] Contrato e cliente TS regenerados
