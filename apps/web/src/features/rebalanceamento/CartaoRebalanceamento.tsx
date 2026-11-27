import { CheckCircle2, Scale } from "lucide-react";
import { Link } from "react-router-dom";
import { plural } from "@/lib/formatacao";
import { usePlano } from "./consultas";

/**
 * Cartão do Dashboard: quantas classes estão fora da banda (plano com aporte 0, carteira
 * inteira). Só aparece quando há metas cadastradas; carregando ou com erro, não ocupa
 * espaço (o Dashboard continua igual).
 */
export function CartaoRebalanceamento() {
  const plano = usePlano("0", "aportes");
  if (!plano.data?.tem_metas) return null;
  const fora = plano.data.classes_fora_da_banda;
  return (
    <section
      aria-label="Rebalanceamento"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card px-4 py-3 text-card-foreground shadow-cartao"
    >
      <p className="flex items-center gap-2 text-sm font-semibold">
        {fora > 0 ? (
          <>
            <Scale aria-hidden className="size-4 text-aviso-texto" />
            {plural(fora, "classe fora da banda", "classes fora da banda")}
            <span className="font-normal text-muted-foreground">
              (tolerância ±{plano.data.tolerancia_pp} p.p.)
            </span>
          </>
        ) : (
          <>
            <CheckCircle2 aria-hidden className="size-4 text-positivo" />
            Carteira dentro das metas
          </>
        )}
      </p>
      <Link
        to="/rebalanceamento"
        className="rounded-sm text-sm font-medium text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        Ver Rebalanceamento
      </Link>
    </section>
  );
}
