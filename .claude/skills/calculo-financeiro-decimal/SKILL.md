---
name: calculo-financeiro-decimal
description: Implementa ou revisa regras de cálculo financeiro do backend (preço médio ponderado, venda parcial e lucro realizado, proventos, desdobramento/grupamento/bonificação, câmbio, accrual de renda fixa, poupança, alocação, série de patrimônio com pandas, resumo mensal) com Decimal e testes de resultado conferido à mão. Use sempre que o usuário pedir ou mudar qualquer cálculo de carteira, rentabilidade, lucro, saldo ou patrimônio.
---

# Cálculos financeiros com Decimal

Os cálculos são regras de negócio **puras e testáveis** em `backend/app/services/` e `backend/app/domain/`: recebem dados, devolvem resultados, sem acessar banco nem rede. Assim dá para testar cada regra isoladamente e confiar nos números que o usuário vê.

## Regras
- **`Decimal` sempre**, construído a partir de string ou inteiro, nunca de `float`. Defina o contexto/precisão e o modo de arredondamento (ex.: `ROUND_HALF_EVEN` ou `ROUND_HALF_UP`) em **um** lugar, documentado, e aplique só na apresentação ou no ponto definido, não a cada passo intermediário.
- **Custo:** preço médio ponderado. Compras recalculam o preço médio; vendas **não** alteram o preço médio, só a quantidade, e geram lucro realizado = (preço de venda − preço médio) × quantidade − taxas.
- **Eventos corporativos:** desdobramento, grupamento e bonificação ajustam quantidade e preço médio mantendo o custo total coerente. Aplique por data, na ordem cronológica junto com as transações.
- **Multimoeda:** ativo em USD convertido para BRL com o **câmbio guardado na data de cada transação** (custo em BRL fica fixo); o valor atual usa o câmbio vigente.
- **Renda fixa:** accrual por indexador (pré, % CDI, IPCA+) a partir de `indicadores`, com origem `calculado`. **Poupança:** regra simplificada, com a simplificação documentada em `docs/`.
- **Proventos e rentabilidade:** deixe explícito o que entra em cada métrica (valor + proventos vs. só valor). Se o tratamento for ambíguo, pergunte antes de implementar.
- **Série de patrimônio:** reconstruída por dia com pandas a partir de transações + histórico de `precos`; preencha dias sem preço com o último valor conhecido (e documente).

## Casos de borda a tratar e testar
Venda maior que a posição (erro de domínio com mensagem pt-BR, sem posição negativa silenciosa), quantidade zero, posição zerada e reaberta, taxas, arredondamento de `Decimal`, ativo sem preço, dia sem transação, datas iguais (ordem estável), câmbio ausente.

## Testes (pytest)
- Dados sintéticos pequenos com **resultado calculado à mão**, e o cálculo escrito no comentário do teste. Exemplo de comentário: `# 10 @ 20 + 10 @ 30 => PM = (200+300)/20 = 25; vende 5 @ 40 => lucro = (40-25)*5 = 75`.
- Cubra: preço médio, venda parcial, proventos, desdobramento/grupamento/bonificação, câmbio, accrual de renda fixa, série de patrimônio e resumo mensal.
- Compare `Decimal` com `Decimal` (nunca com float). Testes sem internet e sem relógio real (injete datas).
