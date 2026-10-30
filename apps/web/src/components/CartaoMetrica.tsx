import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Cartão de métrica: rótulo, valor em destaque e uma linha de apoio. */
export function CartaoMetrica({
  titulo,
  valor,
  apoio,
  carregando = false,
  className,
}: {
  titulo: string;
  valor: ReactNode;
  apoio?: ReactNode;
  carregando?: boolean;
  className?: string;
}) {
  return (
    <section
      aria-label={titulo}
      className={cn(
        "flex min-w-0 flex-col gap-1 rounded-xl border bg-card p-4 text-card-foreground",
        className,
      )}
    >
      <h3 className="text-xs font-medium text-muted-foreground">{titulo}</h3>
      <div className="tabular truncate text-lg font-semibold" aria-busy={carregando}>
        {carregando ? <span className="text-muted-foreground">…</span> : valor}
      </div>
      {apoio && <div className="text-xs text-muted-foreground">{apoio}</div>}
    </section>
  );
}
