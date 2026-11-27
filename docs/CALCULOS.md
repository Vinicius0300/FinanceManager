# Cálculos financeiros

Regras de cálculo do backend, decididas com o dono na Parte 2. O código fica em `backend/app/domain/` (funções puras) e os testes, com os exemplos abaixo conferidos à mão, em `backend/tests/test_dominio_*.py`.

## 1. Números e arredondamento
- Todo valor é `Decimal`, construído de `str`, `int` ou `Decimal` (`domain/numeros.py::dec`). `float` é recusado com erro.
- Contexto de cálculo: 28 dígitos significativos e `ROUND_HALF_EVEN` (arredondamento bancário). Divisão por zero e operação inválida levantam exceção. Divisão e potência usam esse contexto explicitamente (`dividir`, `potencia`).
- **Precisão cheia nos cálculos internos; arredondamento só na apresentação:**
  - `arredondar_moeda`: 2 casas;
  - `arredondar_quantidade`: 8 casas (cripto);
  - `percentual`: converte a razão em % com 2 casas.
- **Exceção:** o movimento de caixa de uma compra ou venda é arredondado a centavos, como no extrato da corretora (ver seção 5). O custo da posição continua com a precisão cheia.
- **Casas decimais aceitas na entrada** (decisão do dono, code review). Um valor com mais casas é **recusado** com "Use no máximo N casas decimais", nunca arredondado em silêncio. Zeros à direita não contam (100,500 é aceito como dinheiro).

  | Campo | Casas |
  |---|---|
  | Dinheiro (aporte, resgate, depósito, saque, taxas, provento, imposto retido, lançamentos) | 2 |
  | Quantidade | 8 |
  | Preço unitário, custo atribuído da bonificação, cotação registrada | 8 |
  | Câmbio | 6 |
- No banco, valores ficam como TEXT exato (`"1234.5600"`), nunca REAL (`repositories/tipos.py::DecimalTexto`).

Exemplo de `ROUND_HALF_EVEN`: 1.010,025 vira 1.010,02 (o 5 exato vai para o vizinho par) e 2,355 vira 2,36.

## 2. Posição em cotas (ações, fundos, cripto)
A posição é calculada por **(ativo, instituição)** (`domain/posicao.py`).

| Operação | Efeito |
|---|---|
| Compra | custo += q × p + taxas; PM = custo / quantidade |
| Venda | custo sai proporcional (custo × q / quantidade; tudo, se zera); lucro = q × p − taxas − custo que saiu; o PM não muda |
| Provento | soma o valor líquido (e o imposto retido) para as métricas; não mexe em PM, custo nem valor da posição |
| Desdobramento / grupamento (`de:para`) | quantidade × para/de; o custo total fica igual |
| Bonificação (`de:para`, custo unitário) | novas = quantidade × (para − de)/de; custo += novas × custo unitário (regra da Receita) |

- **Taxas:** as de compra sobem o PM; as de venda reduzem o lucro. Ex.: compra de 100 @ 10 + 5 de taxa dá custo 1.005 e PM 10,05. A venda de 100 @ 12 com 4 de taxa dá lucro de 1.200 − 4 − 1.005 = **191**.
- **Venda maior que a posição** é erro de domínio, com mensagem em pt-BR; a posição nunca fica negativa. Uma posição zerada e reaberta recomeça o PM do zero.
- **Ordem:** por data. No mesmo dia, o evento corporativo vem antes das transações (a data do evento é a data "ex"); entre transações, vale a ordem de registro.
- **Frações de grupamento** (ex.: 105 ações em 10:1 viram 10,5) são mantidas. O usuário registra a venda da fração no leilão como uma venda comum.
- **Bonificação.** Ex.: 100 @ 10 com bonificação de 10% (10:11) e custo atribuído de R$ 4 dá 110 ações, custo 1.040 e PM 9,4545… Vender as 110 @ 12 gera lucro de 280. Sem custo informado, o custo atribuído é zero.

## 3. Multimoeda
- Cada transação **e cada evento corporativo** guarda o **câmbio da data** (BRL por unidade). Se ele não for informado, vem do indicador de câmbio mais recente com até 7 dias. Sem câmbio, a operação é recusada. No evento, o câmbio só é buscado quando importa (bonificação com custo atribuído); nos demais fica 1. Por estar gravado, cadastrar um câmbio depois não muda o custo em BRL já registrado.
- Custo, lucro e proventos são acumulados na moeda do ativo **e** em BRL (o custo em BRL fica fixo no câmbio de cada compra). O valor atual em BRL usa o câmbio vigente.
- Ex.: compra 10 @ US$ 100 + US$ 1 (câmbio 5) e 10 @ US$ 110 (câmbio 5,5). O custo fica em US$ 2.101 / R$ 11.055. Vender 5 @ US$ 120 (câmbio 6) dá lucro de US$ 74,75 / R$ 836,25.
- A conta corrente em USD fica em USD e é convertida para BRL no patrimônio pelo câmbio vigente.

## 4. Métricas e proventos (opção A)
- Valorização = (valor atual − custo da posição) / custo da posição.
- Resultado total = (valor atual − custo restante) + lucro realizado + proventos líquidos + rendimentos de bonificação.
- **Rentabilidade total = resultado total / total investido** (soma do custo de todas as compras/aportes).
- Exemplos:
  - Compra 100 @ 10, provento 50, cotação 11: valorização **10%** e rentabilidade total **15%**.
  - Vendendo 50 @ 12 (lucro 100), com cotação 11: (550 − 500 + 100 + 50) / 1.000 = **20%**.
- **Bonificação na rentabilidade:** o custo atribuído entra no custo (regra da Receita) e também é reconhecido como rendimento em ações. Sem isso, a rentabilidade ficaria artificialmente menor. Ex.: 100 @ 10, bonificação com custo 40, cotação 12. O resultado é (1.320 − 1.040) + 40 = 320, ou seja, 32% sobre 1.000.
- Imposto retido na fonte (JCP 15%, EUA 30%): fica gravado em campo próprio; as métricas usam o valor líquido.

## 5. Conta corrente da instituição (caixa)
- Cada instituição tem uma conta por moeda, criada automaticamente no primeiro movimento.
- Movimentos:
  - manuais: depósito e saque;
  - automáticos: compra/aporte debita, venda/resgate credita, provento credita o líquido. Compra e venda são arredondadas a centavos: 3 cotas a R$ 1,234567 (= 3,703701) debitam **R$ 3,70**. Uma compra a preço zero sem taxas não gera movimento;
  - receitas e despesas (Parte 8): receita credita (`credito_receita`) e despesa debita (`debito_despesa`) a conta **BRL** da instituição do lançamento;
  - transferências (Parte 8): `transferencia_saida` (valor) na origem e `transferencia_entrada` (valor) no destino, na moeda da transferência; a tarifa é uma despesa separada na origem;
  - ajuste de saldo: depósito não informado (ver abaixo), ligado à transação ou à despesa que o pediu.
- **O saldo nunca fica negativo.** A checagem usa o saldo ao **fim de cada dia** (movimentos do mesmo dia se compensam), a partir da data do lançamento, porque um lançamento retroativo afeta os saldos seguintes.
- Compra ou aporte maior que o saldo: o service devolve o aviso "Você está movimentando mais dinheiro do que o possível dentro desta conta corrente. Atualizar valores?" e não grava nada. Com `aceitar_ajuste=True`, grava a transação e um `ajuste_saldo` pela diferença, que fica visível e editável. Saque maior que o saldo é recusado.
- Despesa (nova, aumentada, antecipada ou levada para outra instituição) segue a mesma regra do aviso e do ajuste. O ajuste fica ligado à despesa: editar a despesa o refaz, excluir a despesa o remove. Ex.: caixa 1.000, despesa 1.500 → ajuste 500, caixa 0; excluir a despesa → caixa 1.000.
- Transferência: a origem precisa cobrir **valor + tarifa** (1.000 + 10 com 1.005 no caixa → recusada, faltam 5). Nunca gera ajuste.
- Vínculo de cada movimento (constraint `vinculo`): compra/venda/provento → só `transacao_id`; receita/despesa → só `lancamento_id`; transferência → só `transferencia_id`; depósito/saque → nenhum; ajuste → `transacao_id`, `lancamento_id` ou nenhum.
- Excluir um depósito, uma venda etc. que deixaria o saldo negativo também é recusado.
- O saldo das contas não rende.

## 6. Renda fixa (accrual em 252 dias úteis, valor bruto)
`domain/renda_fixa.py` e `domain/calendario.py`. Dias úteis são contados em `[aplicação, data)`, sem fins de semana e feriados nacionais:
- fixos;
- 20/11 a partir de 2024;
- móveis, calculados pela Páscoa: Carnaval, Sexta-feira Santa e Corpus Christi.

| Indexador | Fator |
|---|---|
| Pré | (1 + taxa)^(du/252) |
| % CDI | produto, por dia útil, de 1 + ((1 + CDI_dia)^(1/252) − 1) × percentual |
| IPCA+ | IPCA acumulado × (1 + spread)^(du/252) |

- **CDI:** usa o CDI de cada dia da tabela `indicadores` (dia sem valor usa o último conhecido). Exemplos de R$ 10.000 em agosto/2025 (21 dias úteis):
  - 100% do CDI a 14,90%: **10.116,42**;
  - 110% do CDI: **10.128,13**.
- **IPCA:** cada mês entra pro rata pelos dias úteis do mês dentro do período, (1 + IPCA_mês)^(du_no_período/du_do_mês). Um mês ainda sem IPCA publicado usa o último conhecido (simplificação). Ex.: IPCA + 6% com IPCA de 0,40% em agosto/2025: **10.088,87**.
- O rendimento para no vencimento.
- O valor é **bruto** (sem IR/IOF) e tem origem `calculado`. Sem os arredondamentos intermediários da convenção ANBIMA, pode diferir do extrato em centavos.
- **Aporte e resgate** são em R$. Cada aporte rende desde a própria data. O resgate reduz o principal **proporcionalmente ao saldo**: com fração f = resgate / saldo, cada aporte fica com (1 − f) e o lucro realizado é resgate − f × custo. Resgatar exatamente o saldo exibido (ou qualquer valor ≥ o saldo real) zera a posição, e a fração nunca passa de 1; resgatar mais que o saldo exibido é erro.

## 7. Poupança (regra simplificada)
`domain/poupanca.py`:
- O rendimento é creditado no **aniversário mensal**. Entre aniversários o valor não muda.
- Depósitos nos dias 29 a 31 contam a partir do dia 1º do mês seguinte.
- Taxa do mês: 0,5% se a Selic meta no início do período for maior que 8,5% a.a.; senão, 70% da Selic mensalizada, (1 + 0,7 × Selic)^(1/12) − 1.
- **Simplificações:**
  - TR = 0;
  - resgates reduzem todos os depósitos proporcionalmente (a regra real retira primeiro os depósitos mais antigos e perde o rendimento do período em curso).
- Ex.: 1.000 em 10/01 com Selic de 15% vale 1.005,00 em 10/02 e 1.010,025 em 10/03, exibido como 1.010,02.

## 8. Valor atual e cotações
- **Um preço por ativo por dia** (data local de Brasília). Cada coleta do dia atualiza o registro do dia; o último valor do dia é o fechamento. Fechamentos baixados do histórico de uma fonte recebem o instante 18h de Brasília daquele dia. Preço **manual** do dia não é sobrescrito pela coleta do mesmo dia; no dia seguinte a coleta volta a valer.
- **Cotados:** quantidade × último preço salvo até a data. O preço fica **defasado** quando passa da tolerância do tipo: 4 dias corridos para ações, fundos e Tesouro Direto, 1 dia para cripto.
- **Tesouro Direto:** quantidade × PU de venda do dia (Tesouro Transparente). Ex.: 2,5 títulos × PU 4.000,00 = 10.000,00.
- **Compra ou venda pelo valor total (Tesouro Direto):** o preço gravado é valor ÷ quantidade, arredondado a 8 casas. Ex.: R$ 1.066,42 ÷ 0,07 = 15.234,57142857; o custo fica 1.066,4199999999 e o caixa movimenta exatamente R$ 1.066,42. A combinação é recusada se o caixa não puder resultar no valor informado.
- **Renda fixa e poupança** continuam calculadas (origem `calculado`). Ficam **defasadas** só quando falta o indicador recente usado no cálculo: CDI/Selic com mais de 4 dias até a data de referência (a renda fixa para no vencimento), IPCA com mais de 2 meses de atraso (o IPCA de setembro sai por volta de 10/10, então em 29/10 ele é o último esperado). Ex.: CDB % CDI com o último CDI em 02/01 avaliado em 02/03 fica defasado, com o aviso "CDI defasado: último registro em 02/01/2026; o valor usa o último indicador conhecido."
- **Variação do dia** (cotados) = preço atual ÷ fechamento anterior − 1, onde o fechamento anterior é o último preço com data anterior à do preço atual. Na posição, em BRL: quantidade × (atual − anterior) × câmbio vigente. Na carteira: soma das posições ÷ valor delas no fechamento anterior. Ex.: 10 PETR4, fechamento anterior 50,00 e atual 52,50 → +5% e +25,00; numa carteira só com essa ação, +25,00 sobre 500,00 = +5%.
- **Sem nenhuma cotação:** a posição vale o custo (preço médio), com origem `calculado`, defasado e com aviso.
- **Câmbio antigo:** a conversão para BRL usa o último câmbio salvo. Se ele tiver mais de **4 dias** (mesma tolerância das ações), a posição ou a conta fica **defasada**, com o aviso "Câmbio USD/BRL defasado: último registro em dd/mm/aaaa". Ex.: câmbio de 28/08 avaliado em 01/09 está em dia; em 02/09 fica defasado.
- **Falha de câmbio ou de indicador** (nenhum valor registrado) vira `erro` naquela posição. As demais continuam, e o resumo marca `completo = False`.

## 9. Carteira, alocação e patrimônio
- **Análise por Instituição:** posições e caixa de uma instituição.
- **Análise Geral:** soma as posições do mesmo ativo em todas as instituições; o PM consolidado é o custo total dividido pela quantidade total.
- Patrimônio = investimentos (valor atual em BRL) + caixa (saldos em BRL).
- Alocação por tipo de ativo, com a fatia `caixa`.
- Ex. do cenário de teste em 01/09/2025: TST11 1.500 + AAPL 6.600 + CDB 10.116,42 + caixa 1.695 = **19.911,42**.
- **Rentabilidade da carteira** (API): as mesmas métricas da posição (seção 4), somando em BRL os valores de todas as posições avaliadas, inclusive as zeradas (que guardam lucro realizado e proventos). Ex.: compra de 10 a 40,00 (custo 400) cotada a 52,50 → (525 − 400) ÷ 400 = 31,25%.
- **Saída da API:** dinheiro arredondado a 2 casas; preço, quantidade e razões (percentuais como 0,3125) a 8 casas. Os cálculos internos não arredondam.

## 10. Série diária de patrimônio (pandas)
`domain/serie_patrimonio.py`:
- Um ponto por dia corrido, com o valor ao fim do dia.
- Quantidade e custo seguem o histórico de operações.
- Preço e câmbio usam o último valor conhecido. Antes do primeiro preço, a posição vale o custo; antes do primeiro câmbio, usa-se o primeiro disponível.
- Renda fixa e poupança entram pelo accrual de cada dia; o caixa, pelo saldo de fim de dia.
- Falhas não derrubam a série:
  - posição que não pode ser reconstruída entra pelo valor aplicado em BRL (compras/aportes menos vendas/resgates, no câmbio de cada operação, sem rendimento);
  - ativo estrangeiro sem câmbio algum entra pelo custo em BRL;
  - conta sem câmbio algum fica de fora.

  Em todos os casos o motivo vai em `avisos`.
- Há um teste garantindo que o patrimônio de cada dia da série é igual ao da avaliação da carteira naquele dia.

## 11. Receitas e despesas
- Resumo mensal: total recebido, total gasto e saldo (receitas − despesas).
- Totais por categoria, com percentual sobre o total do tipo no mês. Lançamentos sem categoria aparecem como "Sem categoria".
- Proventos **não** entram aqui (ficam na conta corrente da instituição).
- Todo lançamento pertence a uma instituição (Parte 8). Resumo, totais e listagem aceitam filtro por instituição.
- Transferências **não** entram nos totais nem na rosca; a tarifa delas entra como despesa. Ex.: salário 5.000, mercado 800 e transferência de 1.000 com tarifa 10 → Recebido 5.000, Gasto 810, Saldo 4.190.
- Resumo por instituição (só BRL): receitas − despesas (com tarifas) + transferências recebidas − enviadas. Ex.: Nubank 5.000 − 2.010 + 0 − 1.000 = 1.990; Itaú 0 − 3.500 + 1.000 − 0 = −2.500 (o ajuste de saldo não é receita).

## 12. Histórico de operações (Parte 4)
Funções puras em `backend/app/domain/historico.py`; consulta em `services/historico.py`.

- **Resultado da operação** (`resultado` na moeda do ativo e `resultado_brl`): lucro ou prejuízo realizado **daquela** venda/resgate, calculado pela mesma regra do preço médio (seção 2) ou do resgate proporcional (seção 6). É a diferença do lucro realizado acumulado da posição antes e depois da operação, por isso a soma dos resultados de um ativo é exatamente o `lucro_realizado` dele (há teste conferindo).
  - Ex.: 100 a R$ 10 + 100 a R$ 12 (PM 11); venda de 50 a R$ 15 com R$ 5 de taxa → 750 − 5 − 550 = **+R$ 195**; venda dos 150 restantes a R$ 9 → 1.350 − 1.650 = **−R$ 300**; soma −105 = lucro realizado da posição.
  - Moeda estrangeira: AAPL 10 a US$ 100 + US$ 1 (câmbio 5,00 → custo R$ 5.005); venda a US$ 110 − US$ 1 (câmbio 5,50 → R$ 6.044,50). Resultado **+US$ 98** e **+R$ 1.039,50** (o BRL inclui a alta do dólar).
- **Valor total** = movimento de caixa da operação: compra = qtd × preço + taxas e venda = qtd × preço − taxas (a centavos), aporte/resgate = valor, provento = líquido. Em BRL × câmbio da operação.
- **Taxas e imposto** em BRL × câmbio da operação. O cartão "Taxas pagas" soma só taxas e conta as operações com taxa; o IR retido dos proventos é um total à parte (`impostos_retidos`). Estimativa de IR sobre ganho de capital **não** existe no app.
- **Situação do ativo**: posição (ativo + instituição) aberta enquanto tem quantidade/lotes. Com filtro de instituição, vale a posição daquela instituição; sem ele, o ativo está aberto se qualquer instituição ainda tiver posição. Ex.: PETR4 com 100 na XP e zerada na RICO → "ainda na carteira" sem filtro; "encerrada" filtrando RICO.
- **Resumo do filtro**: totais em BRL somados sem arredondar e arredondados a centavos na saída; série mensal do início do filtro (ou da operação mais antiga) até o fim (ou hoje), com os meses sem operação zerados; visão por ativo com os mesmos totais por instituição.
- **Exportação Excel**: números gravados como número (arredondados como na tela) e datas como data `AAAA-MM-DD`; o Excel mostra o separador decimal do Windows.

## 13. Rebalanceamento por metas (Parte 10)
Funções puras em `backend/app/domain/rebalanceamento.py`; leitura das posições, do caixa e das metas em `services/rebalanceamento.py`. O plano é informativo: o app nunca executa ordens.

- **Base:** T = soma do valor atual em BRL das posições abertas (Análise Geral, **sem caixa**); A = aporte (padrão: o caixa de todas as instituições, a centavos); N = T + A. Posição sem valor atual (sem câmbio) fica fora de T, com aviso.
- **Desvio** da classe = % atual (sobre T) − meta, em **pontos percentuais**, com 2 casas. **Fora da banda** se |desvio| > tolerância (padrão 5 p.p.). **Desvio total** = Σ |desvio| ÷ 2 (quanto da carteira está fora do lugar).
- **Só com aportes:** déficit_i = max(0, meta_i × N − atual_i). Se Σ déficits ≥ A, A é dividido na proporção dos déficits; senão, cada déficit é preenchido e a sobra vai pelas metas. Com as metas somando 100%, Σ (meta_i × N − atual_i) = A, então Σ déficits ≥ A sempre; o segundo ramo só aparece no limite Σ déficits = A (nenhuma classe acima da meta), quando cada déficit é preenchido exatamente.
- **Completo:** diferença_i = meta_i × N − atual_i (positivo compra, negativo vende); Σ diferenças = A.
- **Dentro da classe com pesos:** o mesmo algoritmo entre os ativos da classe, com o valor que a classe recebe no lugar de A e os pesos no lugar das metas (ativo sem peso = 0%). No modo só com aportes, classe que recebe 0 não divide nada.
- **Arredondamento:** cada sugestão em centavos (`ROUND_HALF_EVEN`); a diferença para fechar exatamente o total vai, centavo a centavo, para quem perdeu mais no arredondamento (**maior resto**; empate pela ordem de apresentação: maior valor atual, maior meta, slug). Vale para as classes (fecha A) e para os ativos de uma classe (fecha a sugestão da classe). Ex.: 100,00 entre três déficits iguais → 33,34 / 33,33 / 33,33. Sugestão abaixo de R$ 0,01 vira "manter".
- **Venda estimada** (modo completo, ativo com peso): quantidade ≈ venda ÷ preço atual (= venda × quantidade ÷ valor, preço implícito em BRL) e **lucro estimado** = venda − quantidade × preço médio (= venda × (valor − custo) ÷ valor). Renda fixa (sem quantidade): só o lucro, pela proporção. Ex.: PETR4 100 ações, valor 5.000 (preço 50), custo 4.000 (PM 40); vender 2.000 → 40 ações, lucro 2.000 − 40 × 40 = **400**. O app não calcula IR (aviso fixo).

**Exemplo (conferido à mão e em teste):** RF 42.000, Ações BR 28.000, Tesouro 15.000, Ações US 9.000, FII 4.000, Cripto 2.000 (T = 100.000); metas 35/25/15/15/7/3; A = 5.000; N = 105.000.

| Classe | Atual | Meta | Desvio | Alvo (meta × N) | Déficit | Só com aportes | Completo |
|---|---|---|---|---|---|---|---|
| Renda fixa | 42.000 (42%) | 35% | +7 p.p. | 36.750 | 0 | 0,00 | −5.250,00 |
| Ações BR | 28.000 (28%) | 25% | +3 p.p. | 26.250 | 0 | 0,00 | −1.750,00 |
| Tesouro | 15.000 (15%) | 15% | 0 | 15.750 | 750 | 312,50 | +750,00 |
| Ações US | 9.000 (9%) | 15% | −6 p.p. | 15.750 | 6.750 | 2.812,50 | +6.750,00 |
| FII | 4.000 (4%) | 7% | −3 p.p. | 7.350 | 3.350 | 1.395,83 | +3.350,00 |
| Cripto | 2.000 (2%) | 3% | −1 p.p. | 3.150 | 1.150 | 479,17 | +1.150,00 |
| **Total** | 100.000 | 100% | | | 12.000 | **5.000,00** | **5.000,00** |

Só com aportes: Σ déficits 12.000 > 5.000 → proporcional (5.000 × 750 / 12.000 = 312,50; 3.350 → 1.395,833… → 1.395,83; 1.150 → 479,166… → 479,17). Fora da banda de 5 p.p.: Renda fixa (+7) e Ações US (−6). Desvio total = (7 + 3 + 0 + 6 + 3 + 1) ÷ 2 = 10 p.p.
