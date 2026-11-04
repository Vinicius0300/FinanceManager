import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Cartão de métrica: rótulo, valor em destaque, linha de apoio e, quando houver série, uma
 * sparkline à direita (`grafico`). Sem série, o valor ocupa a largura toda.
 */
export function CartaoMetrica({
  titulo,
  valor,
  apoio,
  grafico,
  carregando = false,
  className,
}: {
  titulo: string;
  valor: ReactNode;
  apoio?: ReactNode;
  grafico?: ReactNode;
  carregando?: boolean;
  className?: string;
}) {
  return (
    <section
      aria-label={titulo}
      className={cn(
        "flex min-w-0 flex-col gap-1 rounded-xl border bg-card px-4 py-3.5 text-card-foreground shadow-cartao",
        className,
      )}
    >
      <h3 className="text-xs font-medium text-muted-foreground">{titulo}</h3>
      <div className="tabular text-[1.3rem] leading-tight font-bold" aria-busy={carregando}>
        {carregando ? (
          <span
            aria-label="Carregando"
            className="block h-6 w-32 max-w-full animate-pulse rounded-md bg-muted"
          />
        ) : (
          valor
        )}
      </div>
      {!carregando && (apoio ?? grafico) && (
        <div className="flex min-w-0 items-end gap-3">
          {apoio && <div className="min-w-0 flex-1 text-xs text-muted-foreground">{apoio}</div>}
          {grafico && (
            <div data-testid="sparkline" className="ml-auto w-24 shrink-0 2xl:w-32">
              {grafico}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
