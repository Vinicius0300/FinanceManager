import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { Fragment } from "react";
import { Button } from "@/components/ui/button";
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
  formatarNumero,
  formatarPreco,
  plural,
} from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import { ITENS_POR_PAGINA, type Operacao } from "./consultas";
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
 * Tabela do histórico: ordenação por coluna **na API** (consistente com a paginação),
 * agrupamento por mês quando a ordem é por data, paginação por `limite`/`deslocamento`.
 */
export function TabelaHistorico({
  operacoes,
  total,
  pagina,
  ordem,
  direcao,
  aoOrdenar,
  aoPaginar,
  aoAbrir,
}: {
  operacoes: Operacao[];
  total: number;
  pagina: number;
  ordem: CampoOrdem;
  direcao: Direcao;
  aoOrdenar: (campo: CampoOrdem, direcao: Direcao) => void;
  aoPaginar: (pagina: number) => void;
  aoAbrir: (operacao: Operacao) => void;
}) {
  const ativos = indexarPorId(useAtivos().data);
  const instituicoes = indexarPorId(useInstituicoes().data);
  const tipos = useTiposAtivo().data;
  const paginas = Math.max(1, Math.ceil(total / ITENS_POR_PAGINA));
  const grupos = ordem === "data" ? agruparPorMes(operacoes) : [{ mes: "", itens: operacoes }];

  const linha = (op: Operacao) => {
    const ativo = ativos.get(op.ativo_id);
    const temQuantidade = op.quantidade !== null;
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
        <TableCell className="tabular text-right">
          {temQuantidade ? formatarNumero(op.quantidade) : "—"}
        </TableCell>
        <TableCell className="tabular text-right">
          {temQuantidade ? formatarPreco(op.preco_unitario, op.moeda) : "—"}
        </TableCell>
        <TableCell className="tabular text-right">
          {ehZero(op.taxas) ? "—" : formatarMoeda(op.taxas, op.moeda)}
        </TableCell>
        <TableCell className="tabular text-right">
          {op.tipo === "provento" && !ehZero(op.imposto_retido_brl)
            ? formatarMoeda(op.imposto_retido_brl)
            : "—"}
        </TableCell>
        <TableCell className="tabular text-right">{formatarMoeda(op.valor_total_brl)}</TableCell>
        <TableCell className="text-right">
          {op.tipo === "provento" ? (
            <ValorFinanceiro valor={op.valor_total_brl} seta={false} />
          ) : op.resultado_brl !== null ? (
            <ValorFinanceiro valor={op.resultado_brl} seta={false} />
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </TableCell>
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
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          Mostrando {plural(operacoes.length, "operação", "operações")} de{" "}
          {total.toLocaleString("pt-BR")}
          {ordem === "data" &&
            ` · ordenado por data (${direcao === "desc" ? "mais recentes" : "mais antigas"} primeiro)`}
        </span>
        {paginas > 1 && (
          <nav aria-label="Paginação" className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={pagina <= 1}
              onClick={() => {
                aoPaginar(pagina - 1);
              }}
            >
              <ChevronLeft aria-hidden />
              Anterior
            </Button>
            <span>
              Página {pagina} de {paginas}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={pagina >= paginas}
              onClick={() => {
                aoPaginar(pagina + 1);
              }}
            >
              Próxima
              <ChevronRight aria-hidden />
            </Button>
          </nav>
        )}
      </div>
    </div>
  );
}
