---
titulo: Cotação defasada
categoria: conceitos
sinonimos: Preço defasado, Defasado, Origem do preço
resumo: No app, preço que não pôde ser atualizado: o último valor salvo continua em uso e fica marcado como defasado.
revisado_em: 2026-11
---

## Em uma a três frases

Cotação defasada é um conceito do próprio app Finanças: quando a fonte de preços falha, o app usa o último preço salvo e marca o ativo como **defasado**. Assim a carteira continua funcionando, mas você sabe que aquele valor pode não ser o de hoje.

## Como funciona

O app busca preços em fontes externas (bolsa, Banco Central, Tesouro, CVM) em segundo plano. Se uma fonte estiver fora do ar, sem internet ou sem dado para aquele ativo:

- o ativo mantém o **último preço salvo**;
- a tela mostra o aviso de defasado, com a data e a hora da última atualização;
- os demais ativos continuam sendo atualizados normalmente.

Cada preço guarda a **origem**: `automatico` (veio da fonte), `manual` (você informou) ou `calculado` (o app calculou, como o saldo de um [[cdb]] pelo [[cdi]]). O chip no topo resume quantos ativos estão em dia, defasados ou com erro.

## Exemplo

Você tem 100 [[acao|ações]] cujo último preço salvo, de quinta-feira, é R$ 36,50. Na sexta a fonte não responde:

1. O app continua usando R$ 36,50: posição de 100 × 36,50 = **R$ 3.650,00**, marcada como defasada.
2. Se o preço real de sexta for R$ 37,00, o valor correto seria 100 × 37,00 = **R$ 3.700,00**.
3. A diferença de **R$ 50,00** some assim que a fonte voltar e o preço for atualizado.

## Atenção

- Defasado não é erro de cálculo: o [[patrimonio]] mostrado está certo **para o último preço conhecido**.
- Fins de semana e feriados não deixam ações defasadas: o último fechamento é o preço válido.
- Títulos do [[tesouro-direto]] e fundos são atualizados uma vez por dia; é normal o preço ser do dia útil anterior.
