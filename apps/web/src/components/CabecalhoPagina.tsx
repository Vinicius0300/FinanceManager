import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Título da tela e as ações principais à direita. */
export function CabecalhoPagina({ titulo, acoes }: { titulo: string; acoes?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-xl font-semibold">{titulo}</h1>
      {acoes && <div className="flex flex-wrap items-center gap-2">{acoes}</div>}
    </div>
  );
}

/** Cartão de seção (área de gráfico, tabela, formulário). */
export function Secao({
  titulo,
  acoes,
  children,
  className,
}: {
  titulo?: string;
  acoes?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl border bg-card p-4 text-card-foreground", className)}>
      {(titulo ?? acoes) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {titulo && <h2 className="font-semibold">{titulo}</h2>}
          {acoes}
        </div>
      )}
      {children}
    </section>
  );
}
