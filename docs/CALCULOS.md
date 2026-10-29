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
  - ajuste de saldo: depósito não informado (ver abaixo).
- **O saldo nunca fica negativo.** A checagem usa o saldo ao **fim de cada dia** (movimentos do mesmo dia se compensam), a partir da data do lançamento, porque um lançamento retroativo afeta os saldos seguintes.
- Compra ou aporte maior que o saldo: o service devolve o aviso "Você está movimentando mais dinheiro do que o possível dentro desta conta corrente. Atualizar valores?" e não grava nada. Com `aceitar_ajuste=True`, grava a transação e um `ajuste_saldo` pela diferença, que fica visível e editável. Saque maior que o saldo é recusado.
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
- **Cotados:** quantidade × último preço salvo até a data (a "data" do preço é a data local de Brasília). O preço fica **defasado** quando passa da tolerância do tipo: 4 dias corridos para ações e fundos, 1 dia para cripto.
- **Sem nenhuma cotação:** a posição vale o custo (preço médio), com origem `calculado`, defasado e com aviso.
- **Câmbio antigo:** a conversão para BRL usa o último câmbio salvo. Se ele tiver mais de **4 dias** (mesma tolerância das ações), a posição ou a conta fica **defasada**, com o aviso "Câmbio USD/BRL defasado: último registro em dd/mm/aaaa". Ex.: câmbio de 28/08 avaliado em 01/09 está em dia; em 02/09 fica defasado.
- **Falha de câmbio ou de indicador** (nenhum valor registrado) vira `erro` naquela posição. As demais continuam, e o resumo marca `completo = False`.

## 9. Carteira, alocação e patrimônio
- **Análise por Instituição:** posições e caixa de uma instituição.
- **Análise Geral:** soma as posições do mesmo ativo em todas as instituições; o PM consolidado é o custo total dividido pela quantidade total.
- Patrimônio = investimentos (valor atual em BRL) + caixa (saldos em BRL).
- Alocação por tipo de ativo, com a fatia `caixa`.
- Ex. do cenário de teste em 01/09/2025: TST11 1.500 + AAPL 6.600 + CDB 10.116,42 + caixa 1.695 = **19.911,42**.

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
