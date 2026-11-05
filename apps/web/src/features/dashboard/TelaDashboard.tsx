import { ArrowDownRight, ArrowUpRight, CalendarClock } from "lucide-react";
import { useMemo, useState } from "react";
import { CabecalhoPagina, Secao } from "@/components/CabecalhoPagina";
import { CartaoMetrica } from "@/components/CartaoMetrica";
import { Carregando, EstadoErro, EstadoVazio } from "@/components/Estados";
import { Sparkline } from "@/components/graficos/Sparkline";
import { IndicadorDefasado } from "@/components/IndicadorDefasado";
import { Segmentos } from "@/components/Segmentos";
import { SeletorAnalise } from "@/components/SeletorAnalise";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import {
  nomeDoTipo,
  useAtivos,
  useInstituicaoAnalise,
  useTiposAtivo,
} from "@/lib/consultas-comuns";
import { inicioDaJanela, JANELAS_EVOLUCAO, type JanelaEvolucao } from "@/lib/datas";
import { formatarData, formatarMoeda, formatarRazao } from "@/lib/formatacao";
import {
  useAlocacao,
  useEvolucao,
  useMaiores,
  useResumoMensal,
  useResumoPortfolio,
  useVariacaoDia,
  useVencimentos,
  type Evolucao,
} from "./consultas";
import { GraficoAlocacao, GraficoEvolucao } from "./graficos";
import { separarAltasEBaixas } from "./variacoes";
import { useValoresOcultos } from "@/lib/valores-ocultos";

/**
 * Visão geral (Parte 5A): cartões de métrica (patrimônio com sparkline), evolução com
 * altas e baixas do dia ao lado e, embaixo, alocação, próximos vencimentos e maiores ativos.
 */
export function TelaDashboard({ agora = new Date() }: { agora?: Date }) {
  // Redesenha ao alternar o modo privacidade (os formatadores leem o store).
  useValoresOcultos();
  const instituicaoId = useInstituicaoAnalise();
  // A janela vale para o gráfico de evolução e para a sparkline do patrimônio (mesma consulta).
  const [janela, setJanela] = useState<JanelaEvolucao>("1a");
  const evolucao = useEvolucao(instituicaoId, inicioDaJanela(janela, agora));
  return (
    <div className="flex flex-col gap-3.5">
      <CabecalhoPagina titulo="Dashboard" acoes={<SeletorAnalise />} />
      <Metricas instituicaoId={instituicaoId} agora={agora} evolucao={evolucao.data} />
      <div className="grid gap-3.5 lg:grid-cols-3">
        <EvolucaoPatrimonio
          consulta={evolucao}
          janela={janela}
          aoMudarJanela={setJanela}
          className="lg:col-span-2"
        />
        <Secao titulo="Altas e baixas do dia">
          <AltasEBaixas instituicaoId={instituicaoId} />
        </Secao>
      </div>
      <div className="grid gap-3.5 lg:grid-cols-2 2xl:grid-cols-3">
        <Secao titulo="Alocação">
          <Alocacao instituicaoId={instituicaoId} />
        </Secao>
        <Secao titulo="Próximos vencimentos">
          <ProximosVencimentos instituicaoId={instituicaoId} />
        </Secao>
        <Secao titulo="Maiores ativos" className="lg:col-span-2 2xl:col-span-1">
          <Maiores instituicaoId={instituicaoId} />
        </Secao>
      </div>
    </div>
  );
}

function Metricas({
  instituicaoId,
  agora,
  evolucao,
}: {
  instituicaoId: number | null;
  agora: Date;
  evolucao: Evolucao | undefined;
}) {
  const resumo = useResumoPortfolio(instituicaoId);
  const mensal = useResumoMensal(agora.getFullYear(), agora.getMonth() + 1);
  const serie = useMemo(
    () => (evolucao?.pontos ?? []).map((p) => ({ data: p.data, valor: p.patrimonio })),
    [evolucao],
  );
  if (resumo.isError) {
    return (
      <EstadoErro
        erro={resumo.error}
        aoTentarNovamente={() => {
          void resumo.refetch();
        }}
      />
    );
  }
  const dados = resumo.data;
  const rentabilidade = dados?.rentabilidade;
  const carregando = resumo.isPending;
  const primeiro = serie[0];
  const ultimo = serie.at(-1);
  return (
    <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
      <CartaoMetrica
        titulo="Patrimônio total"
        carregando={carregando}
        valor={formatarMoeda(dados?.patrimonio_brl)}
        grafico={
          primeiro &&
          ultimo && (
            <Sparkline
              pontos={serie}
              rotulo={
                `Evolução do patrimônio de ${formatarData(primeiro.data)} ` +
                `(${formatarMoeda(primeiro.valor)}) a ${formatarData(ultimo.data)} ` +
                `(${formatarMoeda(ultimo.valor)})`
              }
            />
          )
        }
        apoio={
          dados && (
            <>
              Investimentos {formatarMoeda(dados.investimentos_brl)} · Caixa{" "}
              {formatarMoeda(dados.caixa_brl)}
              {!dados.completo && (
                <span className="block text-aviso-texto">
                  Algum valor está sem cotação ou câmbio; o total pode estar incompleto.
                </span>
              )}
            </>
          )
        }
      />
      <CartaoMetrica
        titulo="Variação do dia"
        carregando={carregando}
        valor={<ValorFinanceiro valor={dados?.variacao_dia_brl} />}
        apoio={
          dados?.variacao_dia ? (
            <ValorFinanceiro valor={dados.variacao_dia} percentual />
          ) : (
            "preço atual × fechamento anterior"
          )
        }
      />
      <CartaoMetrica
        titulo="Rentabilidade"
        carregando={carregando}
        valor={
          rentabilidade?.rentabilidade_total ? (
            <ValorFinanceiro valor={rentabilidade.rentabilidade_total} percentual />
          ) : (
            "—"
          )
        }
        apoio={
          rentabilidade && (
            <>
              Resultado <ValorFinanceiro valor={rentabilidade.resultado_total} seta={false} /> sobre{" "}
              {formatarMoeda(rentabilidade.total_investido)} investidos
            </>
          )
        }
      />
      <CartaoMetrica
        titulo="Saldo do mês"
        carregando={mensal.isPending}
        valor={
          mensal.isError ? (
            <span className="text-sm text-negativo">indisponível</span>
          ) : (
            <ValorFinanceiro valor={mensal.data?.saldo} />
          )
        }
        apoio={
          mensal.data &&
          `Recebido ${formatarMoeda(mensal.data.total_receitas)} · Gasto ${formatarMoeda(mensal.data.total_despesas)}`
        }
      />
    </div>
  );
}

function Alocacao({ instituicaoId }: { instituicaoId: number | null }) {
  const alocacao = useAlocacao(instituicaoId);
  if (alocacao.isPending) return <Carregando />;
  if (alocacao.isError) {
    return (
      <EstadoErro
        erro={alocacao.error}
        aoTentarNovamente={() => {
          void alocacao.refetch();
        }}
      />
    );
  }
  if (alocacao.data.length === 0) {
    return (
      <EstadoVazio
        titulo="Nada investido ainda"
        descricao="Cadastre uma instituição, um depósito e um ativo para ver a alocação."
      />
    );
  }
  return <GraficoAlocacao fatias={alocacao.data} />;
}

function EvolucaoPatrimonio({
  consulta,
  janela,
  aoMudarJanela,
  className,
}: {
  consulta: ReturnType<typeof useEvolucao>;
  janela: JanelaEvolucao;
  aoMudarJanela: (janela: JanelaEvolucao) => void;
  className?: string;
}) {
  return (
    <Secao
      titulo="Evolução do patrimônio"
      className={className}
      acoes={
        <Segmentos
          rotulo="Período da evolução"
          opcoes={JANELAS_EVOLUCAO}
          valor={janela}
          aoMudar={aoMudarJanela}
        />
      }
    >
      {consulta.isPending ? (
        <Carregando />
      ) : consulta.isError ? (
        <EstadoErro
          erro={consulta.error}
          aoTentarNovamente={() => {
            void consulta.refetch();
          }}
        />
      ) : consulta.data.pontos.length === 0 ? (
        <EstadoVazio titulo="Sem histórico no período" />
      ) : (
        <>
          <GraficoEvolucao evolucao={consulta.data} />
          {consulta.data.avisos.map((aviso) => (
            <p key={aviso} className="mt-1 text-xs text-aviso-texto">
              {aviso}
            </p>
          ))}
        </>
      )}
    </Secao>
  );
}

function AltasEBaixas({ instituicaoId }: { instituicaoId: number | null }) {
  const variacao = useVariacaoDia(instituicaoId);
  const ativos = useAtivos();
  const simbolos = useMemo(
    () => new Map((ativos.data ?? []).map((a) => [a.id, a.simbolo])),
    [ativos.data],
  );
  if (variacao.isPending) return <Carregando />;
  if (variacao.isError) {
    return (
      <EstadoErro
        erro={variacao.error}
        aoTentarNovamente={() => {
          void variacao.refetch();
        }}
      />
    );
  }
  const { altas, baixas } = separarAltasEBaixas(variacao.data.ativos);
  if (altas.length === 0 && baixas.length === 0) {
    return (
      <EstadoVazio
        titulo="Sem variação para mostrar"
        descricao="A variação aparece quando um ativo cotado tem o preço de hoje e o do dia anterior."
      />
    );
  }
  const lista = (titulo: string, itens: typeof altas, Icone: typeof ArrowUpRight) =>
    itens.length > 0 && (
      <section aria-label={titulo}>
        <h3 className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
          <Icone aria-hidden className="size-3.5" />
          {titulo}
        </h3>
        <ul className="divide-y">
          {itens.map((item) => (
            <li
              key={item.ativo_id}
              className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-1.5 text-[0.8125rem]"
            >
              <span className="truncate font-semibold" title={item.nome}>
                {simbolos.get(item.ativo_id) ?? item.nome}
              </span>
              <ValorFinanceiro valor={item.variacao.variacao} percentual />
              <ValorFinanceiro
                valor={item.variacao.variacao_brl}
                seta={false}
                className="w-24 justify-end"
              />
            </li>
          ))}
        </ul>
      </section>
    );
  return (
    <div className="flex flex-col gap-3">
      {lista("Maiores altas", altas, ArrowUpRight)}
      {lista("Maiores baixas", baixas, ArrowDownRight)}
    </div>
  );
}

function ProximosVencimentos({ instituicaoId }: { instituicaoId: number | null }) {
  const vencimentos = useVencimentos(instituicaoId);
  if (vencimentos.isPending) return <Carregando />;
  if (vencimentos.isError) {
    return (
      <EstadoErro
        erro={vencimentos.error}
        aoTentarNovamente={() => {
          void vencimentos.refetch();
        }}
      />
    );
  }
  if (vencimentos.data.length === 0) {
    return (
      <EstadoVazio
        titulo="Nenhum título a vencer"
        descricao="Renda fixa e Tesouro Direto com posição aberta aparecem aqui, do mais próximo ao mais distante."
      />
    );
  }
  return (
    <Table aria-label="Próximos vencimentos">
      <TableHeader>
        <TableRow>
          <TableHead>Título</TableHead>
          <TableHead>Vencimento</TableHead>
          <TableHead className="text-right">Valor atual</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {vencimentos.data.map((v) => (
          <TableRow key={`${v.ativo_id}-${v.instituicao_id ?? "geral"}`}>
            <TableCell>
              <span className="font-medium">{v.nome}</span>{" "}
              <IndicadorDefasado defasado={v.defasado} aviso={v.aviso} />
            </TableCell>
            <TableCell className="tabular whitespace-nowrap">
              <CalendarClock aria-hidden className="mr-1 inline size-3.5 text-muted-foreground" />
              {formatarData(v.vencimento)}
            </TableCell>
            <TableCell className="tabular text-right">{formatarMoeda(v.valor_brl)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Maiores({ instituicaoId }: { instituicaoId: number | null }) {
  const maiores = useMaiores(instituicaoId);
  const tipos = useTiposAtivo();
  if (maiores.isPending) return <Carregando />;
  if (maiores.isError) {
    return (
      <EstadoErro
        erro={maiores.error}
        aoTentarNovamente={() => {
          void maiores.refetch();
        }}
      />
    );
  }
  if (maiores.data.length === 0) return <EstadoVazio titulo="Nenhuma posição aberta" />;
  return (
    <Table aria-label="Maiores ativos">
      <TableHeader>
        <TableRow>
          <TableHead>Ativo</TableHead>
          <TableHead>Tipo</TableHead>
          <TableHead className="text-right">Valor (BRL)</TableHead>
          <TableHead className="text-right">Participação</TableHead>
          <TableHead className="text-right">Rentabilidade</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {maiores.data.map((p) => (
          <TableRow key={`${p.ativo_id}-${p.instituicao_id ?? "geral"}`}>
            <TableCell>
              <span className="font-medium">{p.simbolo ?? p.nome}</span>{" "}
              <IndicadorDefasado defasado={p.defasado} aviso={p.aviso} erro={p.erro} />
              {p.simbolo && <span className="block text-xs text-muted-foreground">{p.nome}</span>}
            </TableCell>
            <TableCell>{nomeDoTipo(tipos.data, p.tipo)}</TableCell>
            <TableCell className="tabular text-right">{formatarMoeda(p.valor_brl)}</TableCell>
            <TableCell className="tabular text-right">{formatarRazao(p.participacao)}</TableCell>
            <TableCell className="text-right">
              <ValorFinanceiro valor={p.metricas_brl?.rentabilidade_total} percentual />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
