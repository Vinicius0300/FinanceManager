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
import { useState } from "react";
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

/**
 * Tabela com ordenação por coluna (clique no cabeçalho; `aria-sort` para leitores de
 * tela) usando TanStack Table. Linhas clicáveis abrem o detalhe (mouse ou Enter).
 */
export function TabelaDados<T>({
  dados,
  colunas,
  rotulo,
  ordenacaoInicial = [],
  aoClicarLinha,
  idDaLinha,
}: {
  dados: T[];
  // O tipo do valor varia por coluna (padrão do TanStack Table com createColumnHelper).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  colunas: ColumnDef<T, any>[];
  rotulo: string;
  ordenacaoInicial?: SortingState;
  aoClicarLinha?: (item: T) => void;
  idDaLinha?: (item: T) => string;
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
        {tabela.getRowModel().rows.map((linha) => (
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
                <TableCell key={celula.id} className={cn(meta?.numerica && "tabular text-right")}>
                  {flexRender(celula.column.columnDef.cell, celula.getContext())}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
