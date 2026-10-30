import { Loader2 } from "lucide-react";
import { MensagemErro } from "@/components/Estados";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { formatarData, formatarMoeda } from "@/lib/formatacao";
import type { SaldoInsuficiente } from "./saldo";

/**
 * Compra/aporte maior que o saldo: mostra instituição, data e quanto falta.
 * "Cancelar" volta ao formulário (para registrar antes o depósito); "Continuar assim mesmo"
 * reenvia com `aceitar_ajuste=true` e a API cria o ajuste de saldo.
 */
export function DialogoSaldoInsuficiente({
  saldo,
  ocupado,
  erro,
  aoCancelar,
  aoContinuar,
}: {
  saldo: SaldoInsuficiente | null;
  ocupado: boolean;
  erro?: unknown;
  aoCancelar: () => void;
  aoContinuar: () => void;
}) {
  return (
    <AlertDialog
      open={saldo !== null}
      onOpenChange={(aberto) => {
        if (!aberto && !ocupado) aoCancelar();
      }}
    >
      <AlertDialogContent>
        <AlertDialogTitle>Saldo insuficiente</AlertDialogTitle>
        <AlertDialogDescription asChild>
          <div className="grid gap-3">
            <p>
              Você está movimentando mais dinheiro do que há nesta conta corrente. Registre antes o
              depósito ou continue: o app cria um <strong>ajuste de saldo</strong> (depósito não
              informado) pela diferença.
            </p>
            {saldo && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-foreground">
                <dt className="text-muted-foreground">Instituição</dt>
                <dd>
                  {saldo.instituicao} ({saldo.moeda})
                </dd>
                <dt className="text-muted-foreground">Data</dt>
                <dd>{formatarData(saldo.data)}</dd>
                <dt className="text-muted-foreground">Valor que falta</dt>
                <dd className="tabular font-semibold">
                  {formatarMoeda(saldo.valorFaltante, saldo.moeda)}
                </dd>
              </dl>
            )}
          </div>
        </AlertDialogDescription>
        <MensagemErro erro={erro} />
        <AlertDialogFooter>
          <AlertDialogCancel disabled={ocupado}>Cancelar</AlertDialogCancel>
          <Button onClick={aoContinuar} disabled={ocupado}>
            {ocupado && <Loader2 aria-hidden className="animate-spin" />}
            Continuar assim mesmo
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
