---
name: nova-feature-frontend
description: Cria ou altera telas e componentes do frontend React/TypeScript do projeto (Dashboard, Carteira, Movimentações, Receitas e Despesas, Configurações, componentes compartilhados) seguindo o padrão do projeto: tokens de tema, cliente OpenAPI gerado, TanStack Query, Zod em pt-BR, estados de carregamento/vazio/erro e testes. Use sempre que o usuário pedir tela, formulário, gráfico, tabela, filtro ou ajuste visual no front.
---

# Nova feature de frontend

Local: `apps/web/src/features/<feature>/`; compartilhados em `components/`; tokens em `theme/`.

## Regras que não mudam
- **Sem cores ou estilos fixos nos componentes.** Tudo via tokens (CSS variables / classes Tailwind mapeadas a tokens). Tema claro e escuro precisam funcionar. Isso permite trocar o visual sem refatorar.
- **Dinheiro nunca em `number` para cálculo.** Valores chegam como string/decimal da API; use uma lib decimal ou apenas formate (Intl pt-BR). Nada de somar ou multiplicar valores financeiros com `number`.
- **Dados do servidor** via cliente gerado do OpenAPI + TanStack Query. Nunca edite `src/api` à mão; se faltar algo, ajuste o backend e use `contrato-openapi`. Estado de UI no Zustand.
- **URL base e token** vêm do Tauri (`invoke`), nunca fixos.

## Passos
1. Identifique a rota/tela e os endpoints necessários; confirme que existem no cliente gerado.
2. Crie a feature com: página, hooks de dados (`useQuery`/`useMutation`), componentes específicos, schema Zod.
3. **Formulários:** React Hook Form + Zod, mensagens de erro em pt-BR, labels associados, foco gerenciado. Formulário de ativo é **gerado a partir do schema do tipo** exposto pela API (sem hardcode por tipo).
4. **Estados obrigatórios:** carregando (skeleton/spinner), vazio (componente de estado vazio com ação), erro (mensagem compreensível e retry) e backend indisponível. A UI não pode travar durante atualização; invalide/atualize queries pelo stream de eventos.
5. **Exclusões e restauração** exigem diálogo de confirmação.
6. **Dados defasados:** use o indicador compartilhado e mostre data/hora e origem (`automatico`/`manual`/`calculado`) da última atualização.
7. **Gráficos:** ECharts (alocação, evolução, categorias) e Lightweight Charts (séries de preço), com cores vindas dos tokens.
8. **Formatação:** Intl e date-fns em pt-BR (R$, datas, percentuais).
9. **Acessibilidade:** foco visível, navegação por teclado, contraste dos tokens, `aria-label` em ícones.
10. **Testes** (Vitest + Testing Library): formulários (válido, inválido, mensagens pt-BR), formatadores e estados vazio/erro.
11. Rode lint, prettier e `tsc` (strict) e atualize `docs/CONTEXTO.md` se houver decisão nova.

## Checklist rápido
- [ ] Zero cores/estilos fixos
- [ ] Sem aritmética de dinheiro em `number`
- [ ] Carregando, vazio, erro cobertos
- [ ] Confirmação em ações destrutivas
- [ ] Testes e lint passando
