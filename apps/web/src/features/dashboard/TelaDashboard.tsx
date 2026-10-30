import { useState } from "react";
import { CabecalhoPagina, Secao } from "@/components/CabecalhoPagina";
import { CartaoMetrica } from "@/components/CartaoMetrica";
import { Carregando, EstadoErro, EstadoVazio } from "@/components/Estados";
import { IndicadorDefasado } from "@/components/IndicadorDefasado";
import { SeletorAnalise } from "@/components/SeletorAnalise";
import { useInstituicaoAnalise } from "@/lib/consultas-comuns";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { nomeDoTipo, useTiposAtivo } from "@/lib/consultas-comuns";
import { inicioDaJanela, JANELAS_EVOLUCAO, type JanelaEvolucao } from "@/lib/datas";
import { formatarMoeda, formatarRazao } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import {
  useAlocacao,
  useEvolucao,
  useMaiores,
  useResumoMensal,
  useResumoPortfolio,
} from "./consultas";
import { GraficoAlocacao, GraficoEvolucao } from "./graficos";

/** Visão geral: patrimônio (com caixa), variação do dia, rentabilidade, mês, gráficos. */
export function TelaDashboard({ agora = new Date() }: { agora?: Date }) {
  const instituicaoId = useInstituicaoAnalise();
  return (
    <div className="flex flex-col gap-4">
      <CabecalhoPagina titulo="Dashboard" acoes={<SeletorAnalise />} />
      <Metricas instituicaoId={instituicaoId} agora={agora} />
      <div className="grid gap-4 xl:grid-cols-5">
        <Secao titulo="Alocação" className="xl:col-span-2">
          <Alocacao instituicaoId={instituicaoId} />
        </Secao>
        <Evolucao instituicaoId={instituicaoId} agora={agora} />
      </div>
      <Secao titulo="Maiores ativos">
        <Maiores instituicaoId={instituicaoId} />
      </Secao>
    </div>
  );
}

function Metricas({ instituicaoId, agora }: { instituicaoId: number | null; agora: Date }) {
  const resumo = useResumoPortfolio(instituicaoId);
  const mensal = useResumoMensal(agora.getFullYear(), agora.getMonth() + 1);
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
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <CartaoMetrica
        titulo="Patrimônio total"
        carregando={carregando}
        valor={formatarMoeda(dados?.patrimonio_brl)}
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
            <ValorFinanceiro valor={dados.variacao_dia} percentual seta={false} />
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

function Evolucao({ instituicaoId, agora }: { instituicaoId: number | null; agora: Date }) {
  const [janela, setJanela] = useState<JanelaEvolucao>("1a");
  const evolucao = useEvolucao(instituicaoId, inicioDaJanela(janela, agora));
  return (
    <Secao
      titulo="Evolução do patrimônio"
      className="xl:col-span-3"
      acoes={
        <div role="group" aria-label="Período da evolução" className="flex gap-1">
          {JANELAS_EVOLUCAO.map((j) => (
            <button
              key={j.valor}
              type="button"
              aria-pressed={janela === j.valor}
              onClick={() => {
                setJanela(j.valor);
              }}
              className={cn(
                "rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent",
                janela === j.valor && "bg-secondary font-semibold text-secondary-foreground",
              )}
            >
              {j.rotulo}
            </button>
          ))}
        </div>
      }
    >
      {evolucao.isPending ? (
        <Carregando />
      ) : evolucao.isError ? (
        <EstadoErro
          erro={evolucao.error}
          aoTentarNovamente={() => {
            void evolucao.refetch();
          }}
        />
      ) : evolucao.data.pontos.length === 0 ? (
        <EstadoVazio titulo="Sem histórico no período" />
      ) : (
        <>
          <GraficoEvolucao evolucao={evolucao.data} />
          {evolucao.data.avisos.map((aviso) => (
            <p key={aviso} className="mt-1 text-xs text-aviso-texto">
              {aviso}
            </p>
          ))}
        </>
      )}
    </Secao>
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
    <Table>
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
