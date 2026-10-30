import { ArrowDown, ArrowUp } from "lucide-react";
import {
  formatarMoedaComSinal,
  formatarRazaoComSinal,
  tomDoValor,
  type TomValor,
} from "@/lib/formatacao";
import { cn } from "@/lib/utils";

const CLASSE_TOM: Record<TomValor, string> = {
  positivo: "text-positivo",
  negativo: "text-negativo",
  neutro: "text-muted-foreground",
};

/**
 * Ganho ou perda (dinheiro, ou razão da API como percentual quando `percentual`): cor do token **e** sinal (+/−) com seta, nunca só a cor.
 * Zero (ou sem valor) usa `--muted-foreground`.
 */
export function ValorFinanceiro({
  valor,
  moeda = "BRL",
  percentual = false,
  seta = true,
  className,
}: {
  valor: string | null | undefined;
  moeda?: string;
  percentual?: boolean;
  seta?: boolean;
  className?: string;
}) {
  const tom = tomDoValor(valor);
  const texto = percentual ? formatarRazaoComSinal(valor) : formatarMoedaComSinal(valor, moeda);
  const rotuloTom = tom === "positivo" ? "ganho" : tom === "negativo" ? "perda" : undefined;
  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-0.5 whitespace-nowrap",
        CLASSE_TOM[tom],
        className,
      )}
      data-tom={tom}
    >
      {seta && tom === "positivo" && <ArrowUp aria-hidden className="size-3.5" />}
      {seta && tom === "negativo" && <ArrowDown aria-hidden className="size-3.5" />}
      {rotuloTom && <span className="sr-only">{rotuloTom}: </span>}
      {texto}
    </span>
  );
}
