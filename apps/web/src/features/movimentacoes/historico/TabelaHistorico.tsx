import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Fragment } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { ehZero } from "@/lib/decimal";
import {
  indexarPorId,
  nomeDoTipo,
  useAtivos,
  useInstituicoes,
  useTiposAtivo,
} from "@/lib/consultas-comuns";
import {
  formatarData,
  formatarMesAno,
  formatarMoeda,
  formatarQuantidade,
  formatarPreco,
  plural,
} from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import type { Operacao } from "./consultas";
import { agruparPorMes, NOMES_SUBTIPO } from "./rotulos";
import { SeloOperacao } from "./SeloOperacao";
import type { CampoOrdem, Direcao } from "./filtros";

interface ColunaOrdenavel {
  campo: CampoOrdem | null;
  titulo: string;
  numerica?: boolean;
}

const COLUNAS: ColunaOrdenavel[] = [
  { campo: "data", titulo: "Data" },
  { campo: "operacao", titulo: "Operação" },
  { campo: "ativo", titulo: "Ativo" },
  { campo: "instituicao", titulo: "Instituição" },
  { campo: "quantidade", titulo: "Qtd.", numerica: true },
  { campo: "preco_unitario", titulo: "Preço unit.", numerica: true },
  { campo: "taxas", titulo: "Taxas", numerica: true },
  { campo: null, titulo: "Imposto", numerica: true },
  { campo: "valor_total", titulo: "Valor total", numerica: true },
  { campo: "resultado", titulo: "Resultado", numerica: true },
];

/**
 * Colunas de valores de uma operação (Qtd., Preço unit., Taxas, Imposto, Valor total e
 * Resultado), iguais na tabela do histórico e no painel da instituição (visão Por ativo).
 */
export function CelulasValores({ operacao }: { operacao: Operacao }) {
  const tem = operacao.quantidade !== null;
  return (
    <>
      <TableCell className="tabular text-right">
        {tem ? formatarQuantidade(operacao.quantidade) : "—"}
      </TableCell>
      <TableCell className="tabular text-right">
        {tem ? formatarPreco(operacao.preco_unitario, operacao.moeda) : "—"}
      </TableCell>
      <TableCell className="tabular text-right">
        {ehZero(operacao.taxas) ? "—" : formatarMoeda(operacao.taxas, operacao.moeda)}
      </TableCell>
      <TableCell className="tabular text-right">
        {operacao.tipo === "provento" && !ehZero(operacao.imposto_retido_brl)
          ? formatarMoeda(operacao.imposto_retido_brl)
          : "—"}
      </TableCell>
      <TableCell className="tabular text-right">
        {formatarMoeda(operacao.valor_total_brl)}
      </TableCell>
      <TableCell className="text-right">
        {operacao.tipo === "provento" ? (
          <ValorFinanceiro valor={operacao.valor_total_brl} seta={false} />
        ) : operacao.resultado_brl !== null ? (
          <ValorFinanceiro valor={operacao.resultado_brl} seta={false} />
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
    </>
  );
}

/**
 * Tabela do histórico: ordenação por coluna **na API** (consistente com a paginação),
 * agrupamento por mês quando a ordem é por data. A paginação fica no rodapé da seção
 * (`Paginacao`), comum às duas visões.
 */
export function TabelaHistorico({
  operacoes,
  ordem,
  direcao,
  aoOrdenar,
  aoAbrir,
}: {
  operacoes: Operacao[];
  ordem: CampoOrdem;
  direcao: Direcao;
  aoOrdenar: (campo: CampoOrdem, direcao: Direcao) => void;
  aoAbrir: (operacao: Operacao) => void;
}) {
  const ativos = indexarPorId(useAtivos().data);
  const instituicoes = indexarPorId(useInstituicoes().data);
  const tipos = useTiposAtivo().data;
  const grupos = ordem === "data" ? agruparPorMes(operacoes) : [{ mes: "", itens: operacoes }];

  const linha = (op: Operacao) => {
    const ativo = ativos.get(op.ativo_id);
    const detalheAtivo = [
      ativo?.simbolo ? ativo.nome : null,
      op.subtipo_provento ? NOMES_SUBTIPO[op.subtipo_provento] : null,
      ativo ? nomeDoTipo(tipos, ativo.tipo) : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return (
      <TableRow
        key={op.id}
        data-clicavel
        tabIndex={0}
        onClick={() => {
          aoAbrir(op);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") aoAbrir(op);
        }}
      >
        <TableCell className="tabular whitespace-nowrap">{formatarData(op.data)}</TableCell>
        <TableCell>
          <SeloOperacao tipo={op.tipo} />
        </TableCell>
        <TableCell>
          <span className="font-semibold text-info">{ativo?.simbolo ?? ativo?.nome ?? "—"}</span>
          {detalheAtivo && (
            <span className="block text-xs text-muted-foreground">{detalheAtivo}</span>
          )}
        </TableCell>
        <TableCell>{instituicoes.get(op.instituicao_id)?.nome ?? "—"}</TableCell>
        <CelulasValores operacao={op} />
      </TableRow>
    );
  };

  return (
    <div className="flex flex-col gap-2">
      <Table aria-label="Histórico de operações">
        <TableHeader>
          <TableRow>
            {COLUNAS.map((c) => (
              <TableHead
                key={c.titulo}
                className={cn(c.numerica && "text-right")}
                aria-sort={
                  c.campo === ordem ? (direcao === "asc" ? "ascending" : "descending") : undefined
                }
              >
                {c.campo ? (
                  <button
                    type="button"
                    className={cn(
                      "inline-flex items-center gap-1 hover:text-foreground",
                      c.numerica && "flex-row-reverse",
                    )}
                    onClick={() => {
                      const campo = c.campo as CampoOrdem;
                      aoOrdenar(campo, campo === ordem && direcao === "desc" ? "asc" : "desc");
                    }}
                  >
                    {c.titulo}
                    {c.campo === ordem ? (
                      direcao === "asc" ? (
                        <ArrowUp aria-hidden className="size-3" />
                      ) : (
                        <ArrowDown aria-hidden className="size-3" />
                      )
                    ) : (
                      <ArrowUpDown aria-hidden className="size-3 opacity-40" />
                    )}
                  </button>
                ) : (
                  c.titulo
                )}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {grupos.map((grupo) => (
            <Fragment key={grupo.mes || "todos"}>
              {grupo.mes && (
                <TableRow className="bg-muted/60">
                  <TableCell colSpan={COLUNAS.length} className="py-1.5 text-xs">
                    <span className="font-semibold">{formatarMesAno(grupo.mes)}</span>{" "}
                    <span className="text-muted-foreground">
                      {plural(grupo.itens.length, "operação", "operações")}
                    </span>
                  </TableCell>
                </TableRow>
              )}
              {grupo.itens.map(linha)}
            </Fragment>
          ))}
        </TableBody>
      </Table>
      {ordem === "data" && (
        <p className="text-xs text-muted-foreground">
          Ordenado por data ({direcao === "desc" ? "mais recentes" : "mais antigas"} primeiro)
        </p>
      )}
    </div>
  );
}
