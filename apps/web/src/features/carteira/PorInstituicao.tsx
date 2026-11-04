import { keepPreviousData, useQueries, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { createColumnHelper } from "@tanstack/react-table";
import { useMemo } from "react";
import type { components } from "@/api/schema";
import { Carregando, EstadoErro, EstadoVazio } from "@/components/Estados";
import { IndicadorDefasado } from "@/components/IndicadorDefasado";
import { TabelaDados } from "@/components/TabelaDados";
import { TableCell, TableRow } from "@/components/ui/table";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import type { Posicao } from "@/features/dashboard/consultas";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { nomeDoTipo, useTiposAtivo } from "@/lib/consultas-comuns";
import { ehZero } from "@/lib/decimal";
import { formatarMoeda } from "@/lib/formatacao";
import { ordenarDecimal } from "@/lib/ordenacao";
import { subtotalResultado } from "./subtotais";

type ResumoInstituicao = components["schemas"]["ResumoInstituicao"];

const COLUNAS_TOTAIS = 5;

/** Patrimônio de cada instituição (subtotal de Valor, já com o caixa). */
function useResumoInstituicoes() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["portfolio", "instituicoes"],
    queryFn: async ({ signal }) =>
      exigir(await cliente.GET("/api/portfolio/instituicoes", { signal })),
    placeholderData: keepPreviousData,
  });
}

/** Junta as consultas por instituição (função estável: o TanStack memoriza o resultado). */
function juntar(resultados: UseQueryResult<Posicao[]>[]) {
  return {
    posicoes: resultados.flatMap((r) => r.data ?? []),
    carregando: resultados.some((r) => r.isPending),
    falha: resultados.find((r) => r.isError),
  };
}

/** Posições de cada instituição (mesma chave de `usePosicoes`, então o cache é dividido). */
function usePosicoesDasInstituicoes(ids: readonly number[]) {
  const { cliente } = useClienteApi();
  return useQueries({
    combine: juntar,
    queries: ids.map((id) => ({
      queryKey: ["portfolio", "posicoes", id],
      queryFn: async ({ signal }: { signal: AbortSignal }) =>
        exigir(
          await cliente.GET("/api/portfolio/posicoes", {
            params: { query: { instituicao_id: id } },
            signal,
          }),
        ),
      placeholderData: keepPreviousData,
    })),
  });
}

const coluna = createColumnHelper<Posicao>();

/**
 * Carteira por instituição com subtotais (Parte 5A, decisão 9). Cada instituição tem uma
 * linha de subtotal (Valor = patrimônio da API, já com o caixa; Resultado = soma exata das
 * posições), as posições ordenáveis e a linha de caixa. Na Análise por Instituição, só a
 * instituição escolhida aparece.
 */
export function CarteiraPorInstituicao({
  instituicaoId,
  aoAbrir,
}: {
  instituicaoId: number | null;
  aoAbrir: (ativoId: number) => void;
}) {
  const resumo = useResumoInstituicoes();
  const tipos = useTiposAtivo();
  const instituicoes = useMemo(
    () =>
      (resumo.data ?? []).filter(
        (i) => instituicaoId === null || i.instituicao_id === instituicaoId,
      ),
    [resumo.data, instituicaoId],
  );
  const { posicoes, carregando, falha } = usePosicoesDasInstituicoes(
    instituicoes.map((i) => i.instituicao_id),
  );

  const colunas = useMemo(
    () => [
      coluna.accessor((p) => p.simbolo ?? p.nome, {
        id: "ativo",
        header: "Ativo",
        cell: ({ row }) => (
          <span className="flex flex-wrap items-center gap-1 pl-3 font-medium">
            {row.original.simbolo ?? row.original.nome}
            <IndicadorDefasado
              defasado={row.original.defasado}
              aviso={row.original.aviso}
              erro={row.original.erro}
            />
          </span>
        ),
      }),
      coluna.accessor("tipo", {
        header: "Tipo",
        cell: ({ getValue }) => nomeDoTipo(tipos.data, getValue()),
      }),
      coluna.accessor("valor_brl", {
        header: "Valor (BRL)",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue }) => formatarMoeda(getValue()),
      }),
      coluna.accessor((p) => p.metricas_brl?.resultado_total ?? null, {
        id: "resultado",
        header: "Resultado",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue }) => <ValorFinanceiro valor={getValue()} seta={false} />,
      }),
      coluna.accessor((p) => p.metricas_brl?.rentabilidade_total ?? null, {
        id: "rentabilidade",
        header: "Rentabilidade",
        sortingFn: ordenarDecimal,
        meta: { numerica: true },
        cell: ({ getValue }) => <ValorFinanceiro valor={getValue()} percentual />,
      }),
    ],
    [tipos.data],
  );

  if (resumo.isPending || carregando) return <Carregando />;
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
  if (falha) {
    return (
      <EstadoErro
        erro={falha.error}
        aoTentarNovamente={() => {
          void falha.refetch();
        }}
      />
    );
  }
  if (instituicoes.length === 0) {
    return (
      <EstadoVazio
        titulo="Nenhuma instituição cadastrada"
        descricao="Cadastre uma instituição (em Movimentações › Caixa) para ver a carteira por instituição."
      />
    );
  }
  const porId = new Map(instituicoes.map((i) => [String(i.instituicao_id), i]));
  return (
    <TabelaDados
      rotulo="Carteira por instituição"
      dados={posicoes}
      colunas={colunas}
      ordenacaoInicial={[{ id: "valor_brl", desc: true }]}
      idDaLinha={(p) => `${p.ativo_id}-${p.instituicao_id ?? "geral"}`}
      aoClicarLinha={(p) => {
        aoAbrir(p.ativo_id);
      }}
      agrupamento={{
        chave: (p) => String(p.instituicao_id),
        ordem: instituicoes.map((i) => String(i.instituicao_id)),
        cabecalho: (chave, itens) => {
          const instituicao = porId.get(chave);
          return instituicao && <LinhaSubtotal instituicao={instituicao} posicoes={itens} />;
        },
        rodape: (chave) => {
          const instituicao = porId.get(chave);
          if (!instituicao || ehZero(instituicao.caixa_brl)) return null;
          return (
            <TableRow>
              <TableCell className="pl-6">Caixa</TableCell>
              <TableCell className="text-muted-foreground">Saldo em conta</TableCell>
              <TableCell className="tabular text-right">
                {formatarMoeda(instituicao.caixa_brl)}
              </TableCell>
              <TableCell className="text-right text-muted-foreground">—</TableCell>
              <TableCell className="text-right text-muted-foreground">—</TableCell>
            </TableRow>
          );
        },
      }}
    />
  );
}

function LinhaSubtotal({
  instituicao,
  posicoes,
}: {
  instituicao: ResumoInstituicao;
  posicoes: readonly Posicao[];
}) {
  const resultado = subtotalResultado(posicoes);
  const quantas = posicoes.length;
  return (
    <TableRow data-subtotal="true">
      <TableCell colSpan={2}>
        <span className="flex flex-wrap items-center gap-2">
          {instituicao.nome}
          <span className="text-xs font-normal text-muted-foreground">
            {quantas === 0 ? "só caixa" : quantas === 1 ? "1 posição" : `${quantas} posições`}
          </span>
          {!instituicao.completo && (
            <span className="text-xs font-normal text-aviso-texto">total incompleto</span>
          )}
        </span>
      </TableCell>
      <TableCell className="tabular text-right">
        {formatarMoeda(instituicao.patrimonio_brl)}
      </TableCell>
      <TableCell
        className="text-right"
        title={resultado === null ? "Alguma posição está sem resultado." : undefined}
      >
        {resultado === null ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <ValorFinanceiro valor={resultado} seta={false} />
        )}
      </TableCell>
      <TableCell colSpan={COLUNAS_TOTAIS - 4} />
    </TableRow>
  );
}
