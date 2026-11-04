import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type Row,
  type RowData,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Fragment, useState, type ReactNode } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

/** Metadados de coluna: `numerica` alinha à direita com algarismos tabulares. */
declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- assinatura exigida pela biblioteca
  interface ColumnMeta<TData extends RowData, TValue> {
    numerica?: boolean;
  }
}

/** Agrupamento opcional: linhas de subtotal antes/depois das linhas de cada grupo. */
export interface AgrupamentoTabela<T> {
  /** Chave do grupo de cada item (ex.: id da instituição). */
  chave: (item: T) => string;
  /** Ordem dos grupos; grupos fora da lista vêm depois, na ordem em que aparecem. */
  ordem?: readonly string[];
  /** Linhas antes do grupo (ex.: subtotal da instituição). Recebe os itens já ordenados. */
  cabecalho?: (chave: string, itens: T[]) => ReactNode;
  /** Linhas depois do grupo (ex.: caixa da instituição). */
  rodape?: (chave: string, itens: T[]) => ReactNode;
}

/**
 * Tabela com ordenação por coluna (clique no cabeçalho; `aria-sort` para leitores de
 * tela) usando TanStack Table. Linhas clicáveis abrem o detalhe (mouse ou Enter). Com
 * `agrupamento`, a ordenação vale dentro de cada grupo e cada grupo ganha as linhas de
 * subtotal que a tela desenhar. Tabelas largas rolam dentro do próprio contêiner.
 */
export function TabelaDados<T>({
  dados,
  colunas,
  rotulo,
  ordenacaoInicial = [],
  aoClicarLinha,
  idDaLinha,
  agrupamento,
}: {
  dados: T[];
  // O tipo do valor varia por coluna (padrão do TanStack Table com createColumnHelper).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  colunas: ColumnDef<T, any>[];
  rotulo: string;
  ordenacaoInicial?: SortingState;
  aoClicarLinha?: (item: T) => void;
  idDaLinha?: (item: T) => string;
  agrupamento?: AgrupamentoTabela<T>;
}) {
  const [ordenacao, setOrdenacao] = useState<SortingState>(ordenacaoInicial);
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table v8 é o padrão do projeto
  const tabela = useReactTable({
    data: dados,
    columns: colunas,
    state: { sorting: ordenacao },
    onSortingChange: setOrdenacao,
    enableSortingRemoval: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    ...(idDaLinha ? { getRowId: (item: T) => idDaLinha(item) } : {}),
  });

  const abrir = (linha: Row<T>) => {
    aoClicarLinha?.(linha.original);
  };

  const desenharLinha = (linha: Row<T>) => (
    <TableRow
      key={linha.id}
      data-clicavel={aoClicarLinha ? true : undefined}
      tabIndex={aoClicarLinha ? 0 : undefined}
      onClick={
        aoClicarLinha
          ? () => {
              abrir(linha);
            }
          : undefined
      }
      onKeyDown={
        aoClicarLinha
          ? (e) => {
              if (e.key === "Enter") abrir(linha);
            }
          : undefined
      }
    >
      {linha.getVisibleCells().map((celula) => {
        const meta = celula.column.columnDef.meta;
        return (
          <TableCell
            key={celula.id}
            className={cn(meta?.numerica && "tabular text-right whitespace-nowrap")}
          >
            {flexRender(celula.column.columnDef.cell, celula.getContext())}
          </TableCell>
        );
      })}
    </TableRow>
  );

  return (
    <Table aria-label={rotulo}>
      <TableHeader>
        {tabela.getHeaderGroups().map((grupo) => (
          <TableRow key={grupo.id}>
            {grupo.headers.map((cabecalho) => {
              const meta = cabecalho.column.columnDef.meta;
              const sentido = cabecalho.column.getIsSorted();
              const podeOrdenar = cabecalho.column.getCanSort();
              const conteudo = flexRender(
                cabecalho.column.columnDef.header,
                cabecalho.getContext(),
              );
              return (
                <TableHead
                  key={cabecalho.id}
                  className={cn(meta?.numerica && "text-right")}
                  aria-sort={
                    sentido === "asc" ? "ascending" : sentido === "desc" ? "descending" : undefined
                  }
                >
                  {podeOrdenar ? (
                    <button
                      type="button"
                      className={cn(
                        "inline-flex items-center gap-1 hover:text-foreground",
                        meta?.numerica && "flex-row-reverse",
                      )}
                      onClick={cabecalho.column.getToggleSortingHandler()}
                    >
                      {conteudo}
                      {sentido === "asc" ? (
                        <ArrowUp aria-hidden className="size-3" />
                      ) : sentido === "desc" ? (
                        <ArrowDown aria-hidden className="size-3" />
                      ) : (
                        <ArrowUpDown aria-hidden className="size-3 opacity-40" />
                      )}
                    </button>
                  ) : (
                    conteudo
                  )}
                </TableHead>
              );
            })}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {agrupamento
          ? agruparLinhas(tabela.getRowModel().rows, agrupamento).map(([chave, linhas]) => {
              const itens = linhas.map((l) => l.original);
              return (
                <Fragment key={chave}>
                  {agrupamento.cabecalho?.(chave, itens)}
                  {linhas.map(desenharLinha)}
                  {agrupamento.rodape?.(chave, itens)}
                </Fragment>
              );
            })
          : tabela.getRowModel().rows.map(desenharLinha)}
      </TableBody>
    </Table>
  );
}

/** Separa as linhas (já ordenadas) por grupo, na ordem pedida (grupos de `ordem` sem
 * linhas continuam, para a tela mostrar o subtotal de quem só tem caixa). */
function agruparLinhas<T>(
  linhas: readonly Row<T>[],
  agrupamento: Pick<AgrupamentoTabela<T>, "chave" | "ordem">,
): [string, Row<T>[]][] {
  const grupos = new Map<string, Row<T>[]>();
  for (const chave of agrupamento.ordem ?? []) grupos.set(chave, []);
  for (const linha of linhas) {
    const chave = agrupamento.chave(linha.original);
    const lista = grupos.get(chave);
    if (lista) lista.push(linha);
    else grupos.set(chave, [linha]);
  }
  return [...grupos];
}
