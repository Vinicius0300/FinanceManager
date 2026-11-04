import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Título da tela e as ações principais à direita (quebram linha em janelas estreitas). */
export function CabecalhoPagina({ titulo, acoes }: { titulo: string; acoes?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-[1.35rem] leading-tight font-bold">{titulo}</h1>
      {acoes && <div className="flex flex-wrap items-center gap-2">{acoes}</div>}
    </div>
  );
}

/** Cartão de seção (área de gráfico, tabela, formulário), com título e ações à direita. */
export function Secao({
  titulo,
  acoes,
  children,
  className,
}: {
  titulo?: ReactNode;
  acoes?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "min-w-0 rounded-xl border bg-card px-4 py-3.5 text-card-foreground shadow-cartao",
        className,
      )}
    >
      {(titulo ?? acoes) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {titulo && <h2 className="flex items-center gap-2 text-[0.85rem] font-bold">{titulo}</h2>}
          {acoes}
        </div>
      )}
      {children}
    </section>
  );
}
