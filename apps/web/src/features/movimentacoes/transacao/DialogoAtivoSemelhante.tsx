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
import type { AtivoSemelhante } from "./saldo";

/**
 * Renda fixa com os mesmos emissor, indexador, taxa e vencimento de um título que você já
 * tem: "Somar ao existente" grava como aporte nele (cada parcela rende desde a própria
 * data); "Criar título separado" cadastra outro. "Cancelar" volta ao formulário.
 */
export function DialogoAtivoSemelhante({
  semelhante,
  ocupado,
  erro,
  aoCancelar,
  aoSomar,
  aoSeparar,
}: {
  semelhante: AtivoSemelhante | null;
  ocupado: boolean;
  erro?: unknown;
  aoCancelar: () => void;
  aoSomar: () => void;
  aoSeparar: () => void;
}) {
  return (
    <AlertDialog
      open={semelhante !== null}
      onOpenChange={(aberto) => {
        if (!aberto && !ocupado) aoCancelar();
      }}
    >
      <AlertDialogContent>
        <AlertDialogTitle>Você já tem este título</AlertDialogTitle>
        <AlertDialogDescription asChild>
          <div className="grid gap-2">
            <p>
              Já existe um título com os mesmos dados: <strong>{semelhante?.nome}</strong>.
              Registrar esta aplicação como aporte nele ou criar um título separado?
            </p>
            {semelhante?.resumo && <p className="text-xs">{semelhante.resumo}</p>}
          </div>
        </AlertDialogDescription>
        <MensagemErro erro={erro} />
        <AlertDialogFooter>
          <AlertDialogCancel disabled={ocupado}>Cancelar</AlertDialogCancel>
          <Button variant="outline" onClick={aoSeparar} disabled={ocupado}>
            Criar título separado
          </Button>
          <Button onClick={aoSomar} disabled={ocupado}>
            {ocupado && <Loader2 aria-hidden className="animate-spin" />}
            Somar ao existente
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
