---
name: contrato-openapi
description: Regenera e verifica o contrato OpenAPI do backend (docs/openapi.json) e o cliente/tipos TypeScript em apps/web/src/api, falhando se estiverem desatualizados. Use sempre que a API do backend mudar (rotas, schemas, respostas, erros), antes de commitar ou gerar build, ou quando o front reclamar de tipo inexistente vindo do cliente gerado.
---

# Contrato OpenAPI e cliente TypeScript

O contrato é a ponte entre backend e frontend: o FastAPI gera o OpenAPI, e dele saem `docs/openapi.json` e o cliente TS. Se divergirem, o front quebra em runtime sem aviso, então o build e o CI precisam **falhar** quando o contrato gerado difere do commitado.

## Fluxo
1. Use o script de geração em `scripts/` (ver README; ele exporta o OpenAPI direto da aplicação, sem precisar subir o servidor e sem exigir token). Se ainda não existir, crie-o: exporta `app.openapi()` para `docs/openapi.json` e roda o gerador (openapi-typescript ou orval) apontando para `apps/web/src/api`.
2. **Nunca edite o cliente gerado à mão.** Corrija a causa no backend (schema, `response_model`, `summary`, `operation_id`) e regere.
3. Rode o **modo de checagem** do script: gera num diretório temporário e compara com o que está commitado; sai com código diferente de zero se houver diferença. Esse modo é o que o build do instalador e o CI executam.
4. Rode `tsc` (strict) e os testes do front depois de regerar, porque mudanças de contrato quebram chamadas existentes.
5. Commite juntos: mudança de backend + `docs/openapi.json` + cliente gerado.

## Dicas
- Defina `operation_id` estáveis e legíveis para evitar nomes de função gerados que mudam a cada refatoração.
- Mantenha `Decimal` serializado como string no schema para o front não perder precisão.
- Saída determinística: ordene chaves/paths para o diff ser estável.
- Se o diff aparece sem mudança real, verifique versões das ferramentas (fixe versões no lockfile).
