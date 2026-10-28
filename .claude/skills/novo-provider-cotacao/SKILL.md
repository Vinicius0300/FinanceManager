---
name: novo-provider-cotacao
description: Cria ou altera um provider de cotação/indicadores (yfinance, CoinGecko, API SGS do Banco Central, Tesouro Transparente ou uma nova fonte) no backend, com timeout, retry com backoff, rate limit, cache, fallback e testes com rede mockada. Use sempre que o usuário pedir uma nova fonte de preços, corrigir erro de cotação, trocar de fonte ou integrar outra API de dados financeiros.
---

# Novo provider de cotação

Cada fonte é uma classe separada em `backend/app/providers/`, que implementa a interface comum (Protocol/ABC) e é registrada no registry de providers. Isso permite trocar ou adicionar fontes sem tocar no resto, e garante que a falha de uma fonte não derrube o app.

## Passos
1. **Implemente a classe** do provider seguindo a interface comum. Normalize símbolos e moedas na borda (ex.: ações BR com sufixo `.SA` no yfinance; símbolo externo vem de `ativos`).
2. **Resiliência (obrigatória):**
   - timeout explícito em toda chamada de rede;
   - retry com backoff exponencial para erros transitórios;
   - tratamento de rate limit (respeitar `Retry-After`/HTTP 429);
   - cache de curta duração para evitar chamadas repetidas;
   - fallback para outro provider quando houver mais de uma opção para o tipo.
3. **Erros nunca propagam como crash.** Registre em log (arquivo rotativo), devolva um resultado de erro tipado e deixe o ciclo de atualização continuar com os demais ativos. O ativo fica com estado de erro e, sem cotação nova, usa o último valor salvo marcado como **defasado**.
4. **Grave em `precos`:** data/hora, valor em `Decimal`, moeda, **origem** (`automatico`) e nome do provider. Guarde o fechamento diário desde o início (insumo para modelos futuros).
5. **Registre no registry** e vincule ao(s) tipo(s) de ativo pelo nome do provider no handler (ver `novo-tipo-de-ativo`).
6. **Testes sem internet:** mocks de rede (ex.: `respx`/`responses`/monkeypatch). Cubra: sucesso, timeout, retry que se recupera, esgotamento de retries, HTTP 429, resposta malformada, símbolo inexistente e fallback. Nenhum teste pode depender de rede real.
7. **Indicadores** (Selic, CDI, IPCA, PTAX): alimentam `indicadores` e o accrual de renda fixa; confira unidade e periodicidade da série antes de gravar.
8. **Documente** a fonte, limites conhecidos e o símbolo esperado em `docs/CONTEXTO.md`.

## Cuidados
- Dinheiro sempre `Decimal` (converta a partir de string, nunca de `float` direto).
- Não bloqueie a API: chamadas de rede em contexto assíncrono ou em thread/worker do scheduler.
- Atualização manual forçada e scheduler usam lock; não duplique execuções simultâneas.
