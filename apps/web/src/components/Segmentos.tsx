import { useRef, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

export interface OpcaoSegmento<V extends string> {
  valor: V;
  rotulo: string;
}

/**
 * Controle segmentado (ex.: "Análise Geral | Por Instituição", "6M | 1A | Máx"): grupo de
 * botões com `aria-pressed`. Setas ←/→ (e Home/End) movem o foco e escolhem a opção.
 */
export function Segmentos<V extends string>({
  opcoes,
  valor,
  aoMudar,
  rotulo,
  className,
}: {
  opcoes: readonly OpcaoSegmento<V>[];
  valor: V;
  aoMudar: (valor: V) => void;
  rotulo: string;
  className?: string;
}) {
  const grupo = useRef<HTMLDivElement>(null);

  const mover = (e: KeyboardEvent<HTMLButtonElement>, indice: number) => {
    const ultimo = opcoes.length - 1;
    const destino =
      e.key === "ArrowRight"
        ? indice === ultimo
          ? 0
          : indice + 1
        : e.key === "ArrowLeft"
          ? indice === 0
            ? ultimo
            : indice - 1
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? ultimo
              : null;
    const opcao = destino === null ? undefined : opcoes[destino];
    if (destino === null || !opcao) return;
    e.preventDefault();
    aoMudar(opcao.valor);
    grupo.current?.querySelectorAll("button")[destino]?.focus();
  };

  return (
    <div
      ref={grupo}
      role="group"
      aria-label={rotulo}
      className={cn("inline-flex shrink-0 rounded-lg border bg-muted p-0.5", className)}
    >
      {opcoes.map((opcao, indice) => {
        const ativo = opcao.valor === valor;
        return (
          <button
            key={opcao.valor}
            type="button"
            aria-pressed={ativo}
            tabIndex={ativo ? 0 : -1}
            onClick={() => {
              aoMudar(opcao.valor);
            }}
            onKeyDown={(e) => {
              mover(e, indice);
            }}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground",
              ativo &&
                "bg-accent text-accent-foreground shadow-cartao hover:text-accent-foreground",
            )}
          >
            {opcao.rotulo}
          </button>
        );
      })}
    </div>
  );
}
