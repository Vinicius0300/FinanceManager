import { AlertTriangle, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";

/**
 * Selo de dado defasado (cotação ou indicador antigo) e/ou com erro do provider.
 * O motivo aparece no `title` (dica ao passar o mouse) e para leitores de tela.
 */
export function IndicadorDefasado({
  defasado,
  aviso,
  erro,
}: {
  defasado: boolean;
  aviso?: string | null;
  erro?: string | null;
}) {
  if (!defasado && !erro) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {defasado && (
        <Badge variant="aviso" title={aviso ?? "Valor desatualizado."}>
          <Clock aria-hidden />
          Defasado
          {aviso && <span className="sr-only">: {aviso}</span>}
        </Badge>
      )}
      {erro && (
        <Badge variant="perigo" title={erro}>
          <AlertTriangle aria-hidden />
          Erro
          <span className="sr-only">: {erro}</span>
        </Badge>
      )}
    </span>
  );
}
