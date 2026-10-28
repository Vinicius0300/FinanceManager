---
name: novo-tipo-de-ativo
description: Adiciona um novo tipo de ativo ao registry de handlers do backend (ex.: COE, previdência, FII, debênture, ouro, imóvel) sem alterar os tipos existentes. Use sempre que o usuário pedir para suportar um novo tipo de investimento, novos campos específicos de um ativo, ou perguntar "como cadastrar um 7º tipo", mesmo que não mencione "handler" ou "registry".
---

# Novo tipo de ativo

Os tipos de ativo são extensíveis por design: cada tipo é um **handler** isolado em `backend/app/asset_types/`, registrado num registry. Adicionar um tipo não pode exigir editar os outros (princípio aberto/fechado), porque assim um tipo novo nunca quebra o cálculo dos existentes.

## Passos
1. **Defina o tipo** com o usuário se faltar algo: nome interno (slug), moeda padrão, como se obtém o valor atual (cotação por provider, accrual `calculado` ou manual), campos específicos e regras de validação.
2. **Crie o handler** em `asset_types/<slug>.py` seguindo a interface dos handlers existentes. Ele deve declarar:
   - como calcular o **valor atual** (usando `Decimal`);
   - o **nome do provider** a usar (só o nome; o provider em si vive em `providers/`). Se o tipo não tem cotação pública, use último valor salvo (marcar defasado) ou `calculado`;
   - o **schema de campos específicos** (alimenta o formulário do front via endpoint de schema por tipo);
   - a **validação** desses campos, com mensagens em pt-BR.
3. **Registre** o handler no registry (um único ponto de registro). Confirme que nenhum outro handler foi modificado.
4. **Persistência:** os campos específicos vão no JSON de metadados de `ativos`. Só crie migração se houver mudança de coluna (ver `nova-migracao-alembic`); em geral não é necessário.
5. **Se o tipo usa provider novo**, use a skill `novo-provider-cotacao`.
6. **Testes** em `backend/tests/`: validação (válido, inválido, campos faltando), cálculo do valor atual com resultado conferido à mão, e um teste que garante que o registry expõe o novo tipo e o schema de campos.
7. **Contrato:** se o endpoint de tipos/schema mudou de forma, rode `contrato-openapi`.
8. **Frontend:** o formulário é gerado a partir do schema; verifique que o novo tipo aparece e valida sem código específico. Só crie componente próprio se um campo exigir um controle inédito.
9. **Documentação:** acrescente o tipo (ou o exemplo do "7º tipo") em `docs/CONTEXTO.md`.

## Checklist rápido
- [ ] Nenhum handler existente foi alterado
- [ ] Valor atual em `Decimal`, com arredondamento documentado
- [ ] Schema de campos e validação com mensagens pt-BR
- [ ] Testes passando sem internet
- [ ] Docs atualizadas
