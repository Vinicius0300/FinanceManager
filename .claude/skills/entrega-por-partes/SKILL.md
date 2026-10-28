---
name: entrega-por-partes
description: Fluxo padrão para qualquer tarefa de implementação do projeto Finanças, que avança em partes sequenciais validadas pelo dono. Use sempre que o usuário disser "Parte N", "próxima parte", "implemente", "entregue" ou pedir uma funcionalidade nova, mesmo sem citar o fluxo. Garante leitura prévia do contexto, perguntas antes de decisões ambíguas, não adiantar etapas futuras e entrega com comandos, checklist e roteiro de validação.
---

# Entrega por partes

O dono valida cada parte antes da seguinte. Adiantar etapas gera retrabalho e tira o controle dele sobre as decisões, por isso o fluxo abaixo existe.

## 1. Antes de escrever código
1. Leia `CLAUDE.md` e `docs/CONTEXTO.md` (regras, decisões definitivas, roadmap). Se o pedido citar uma parte, confirme em que ponto do roadmap ela está.
2. Delimite o escopo: liste o que está **dentro** da parte e o que pertence a partes futuras. Não implemente o segundo grupo, mesmo que seja fácil (ex.: não criar telas na parte de API, não criar tabelas de IA antes da hora).
3. Procure ambiguidades que mudem o resultado (método de custo, tratamento de proventos, formato de dados, biblioteca). Se houver, **pergunte antes de implementar**, agrupando as dúvidas numa lista curta. Se não houver, diga "sem dúvidas que impactem o escopo" e comece.
4. Se a tarefa depender de material do usuário (por exemplo imagens de referência), analise primeiro e **espere confirmação** antes de alterar código.

## 2. Durante a implementação
- Siga as regras inegociáveis do `CLAUDE.md` (Decimal, tokens de tema, token na API, falhas nunca derrubam o app).
- Entregue por feature, com código completo dos arquivos (sem "..." nem trechos omitidos).
- Escreva testes junto com o código; dados sintéticos com resultado conferido à mão, explicado em comentário.
- Se uma exigência não couber na estrutura atual, avise e proponha alternativa em vez de contornar em silêncio.

## 3. Formato da entrega
Termine sempre com estas seções, nesta ordem:
1. **O que foi feito**: 3 a 6 linhas.
2. **Como rodar**: comandos de instalação, execução e testes (Windows/PowerShell).
3. **O que conferir**: lista objetiva de itens que o dono deve verificar.
4. **Roteiro de validação manual**: passos curtos e concretos com resultado esperado (ex.: cadastrar uma ação, uma compra, um CDB e uma despesa, e conferir Dashboard e Carteira).
5. **Decisões novas**: o que foi decidido e foi registrado em `docs/CONTEXTO.md`.

## 4. Fechamento
- Atualize `docs/CONTEXTO.md` (e `README.md` se mudou o dia a dia).
- Rode a "definição de pronto" do `CLAUDE.md`.
- Declare explicitamente: "Não avancei para a Parte N+1."
