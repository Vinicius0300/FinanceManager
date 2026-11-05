---
name: novo-termo-glossario
description: Acrescenta, revisa ou corrige termos do Glossário do app (verbetes em Markdown com grafo de conhecimento em apps/web/src/features/glossario/conteudo). Use sempre que o usuário pedir um termo novo, um conceito que ficou faltando, correção de explicação, exemplo ou regra de imposto no glossário, ou disser "coloca X no glossário", mesmo sem citar arquivos.
---

# Novo termo do glossário

O glossário é **fixo e só leitura**: cada termo é um arquivo `apps/web/src/features/glossario/conteudo/<slug>.md`, embutido no build. Não há backend, banco nem edição pela tela (decisão do dono, `docs/CONTEXTO.md` 8.8). As ligações do grafo saem dos links `[[slug]]` do texto.

## Passos
1. **Confira se já existe** um termo igual ou um sinônimo (`sinonimos` dos arquivos). Se existir, proponha ampliar o verbete em vez de criar outro.
2. **Slug:** minúsculas, sem acento, palavras separadas por hífen (`tesouro-ipca`, `come-cotas`). O nome do arquivo é o slug.
3. **Frontmatter** (uma linha `chave: valor` por campo, sem aspas):
   ```
   ---
   titulo: Come-cotas
   categoria: impostos
   sinonimos: Antecipação semestral de IR
   resumo: Uma frase que aparece no tooltip do grafo e na busca.
   revisado_em: AAAA-MM
   ---
   ```
   Categorias válidas (ordem fixa, cada uma com a sua cor): `conceitos`, `indicadores`, `renda-fixa`, `renda-variavel`, `impostos`, `planejamento`.
4. **Corpo**: exatamente estas seções `##`, nesta ordem, com 150 a 350 palavras no total:
   - `## Em uma a três frases`
   - `## Como funciona`
   - `## Exemplo`: **sempre com números** em R$, conta passo a passo, taxas redondas e ditas ilustrativas ("CDI de 10% a.a., para facilitar a conta"). Tabela Markdown quando ajudar.
   - `## Atenção`: pegadinhas e confusões comuns.
   Não escreva "Relacionados" nem a data: a tela gera.
5. **Ligações:** cite com `[[slug]]` ou `[[slug|texto exibido]]` só termos que existam. Dentro de tabela use `[[slug\|texto]]`. Avalie citar o termo novo em verbetes antigos onde ele é mencionado, para o grafo ficar bem ligado (todo termo precisa de pelo menos uma ligação).
6. **Confira as contas à mão** (e mostre-as no texto). Regras tributárias e limites (alíquotas, isenções, FGC) conforme a legislação vigente na data de `revisado_em`; em caso de dúvida sobre mudança recente, pergunte ou pesquise antes de escrever.
7. **Valide e formate** (na raiz):
   - `npm test` (o `conteudo.test.ts` aponta link quebrado, seção fora do modelo, tamanho, categoria, termo isolado);
   - `npm run format` (o Prettier alinha as tabelas) e `npm run format:check`.
8. Se um termo citado nas **sugestões iniciais** (`SUGESTOES_INICIAIS` em `TelaGlossario.tsx`) passar a existir, ele aparece sozinho; não precisa mexer no código.
9. Registre em `docs/CONTEXTO.md` só se surgir decisão nova (categoria nova, mudança de modelo).

## Cuidados
- Texto em pt-BR, simples e educativo; nada de recomendação de investimento.
- Sem HTML no Markdown (a tela ignora); sem links externos (viram texto).
- Categoria nova exige mudar `dominio/categorias.ts` e há só 6 cores de gráfico: pergunte ao dono antes.
