---
name: nova-migracao-alembic
description: Altera o schema do banco SQLite do projeto (nova tabela, coluna, índice, constraint ou enum) criando e validando uma migração Alembic segura, com backup prévio e dados preservados. Use sempre que o usuário pedir mudança de modelo de dados, nova entidade, novo índice ou campo novo, e antes de qualquer alteração em models do SQLAlchemy.
---

# Nova migração Alembic

As migrações rodam **automaticamente** na inicialização do backend, com backup prévio do banco. Como o banco é do usuário final e está em `%APPDATA%\Financas\`, uma migração ruim pode corromper dados reais; por isso cada migração precisa ser reversível quando possível e testada contra dados existentes.

## Passos
1. **Altere os models** (SQLAlchemy 2.0) em um só lugar. Mantenha: chaves estrangeiras, constraints de integridade (CHECK, UNIQUE, NOT NULL) e índices relevantes (ex.: `(ativo_id, data)` em tabelas de séries). Dinheiro como tipo decimal adequado (nunca float).
2. **Gere a migração** com autogenerate e **revise à mão** o arquivo gerado. O autogenerate erra com SQLite (alterações de coluna exigem `batch_alter_table`). Dê um nome descritivo à revisão.
3. **SQLite:** use `op.batch_alter_table` para alterar/remover colunas e constraints; habilite verificação de chaves estrangeiras onde for preciso.
4. **Dados existentes:** se a mudança afeta linhas já gravadas, escreva a migração de dados (valores padrão, backfill) na mesma revisão. Não assuma banco vazio.
5. **Teste:**
   - `upgrade head` em banco vazio;
   - `upgrade` a partir da revisão anterior com dados sintéticos preenchidos, conferindo que os dados sobrevivem;
   - `downgrade` quando a migração for reversível (se não for, deixe isso explícito no docstring).
6. **Alembic em runtime:** confirme que a rotina de inicialização cria o backup antes de migrar e que falha de migração não deixa o banco pela metade (aborta com mensagem clara e preserva o backup).
7. **Não crie tabelas de partes futuras** (ex.: `previsoes`, `sugestoes` só existem no plano em `docs/`).
8. **Se o schema da API mudou** por causa dos models, rode `contrato-openapi`.
9. Registre a decisão de modelagem em `docs/CONTEXTO.md`.

## Checklist rápido
- [ ] Autogenerate revisado manualmente
- [ ] `batch_alter_table` onde necessário
- [ ] Testado em banco vazio e com dados
- [ ] Backup prévio preservado em caso de falha
