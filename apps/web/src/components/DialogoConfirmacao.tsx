import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
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

/**
 * Confirmação antes de exclusões e da restauração. Fica aberto durante a operação
 * (o botão mostra o progresso) e exibe a mensagem da API se ela recusar
 * (ex.: "Não é possível excluir um ativo com transações").
 */
export function DialogoConfirmacao({
  aberto,
  aoMudar,
  titulo,
  descricao,
  textoConfirmar = "Excluir",
  destrutivo = true,
  ocupado = false,
  erro,
  aoConfirmar,
}: {
  aberto: boolean;
  aoMudar: (aberto: boolean) => void;
  titulo: string;
  descricao: ReactNode;
  textoConfirmar?: string;
  destrutivo?: boolean;
  ocupado?: boolean;
  erro?: unknown;
  aoConfirmar: () => void;
}) {
  return (
    <AlertDialog open={aberto} onOpenChange={aoMudar}>
      <AlertDialogContent>
        <AlertDialogTitle>{titulo}</AlertDialogTitle>
        <AlertDialogDescription asChild>
          <div>{descricao}</div>
        </AlertDialogDescription>
        <MensagemErro erro={erro} />
        <AlertDialogFooter>
          <AlertDialogCancel disabled={ocupado}>Cancelar</AlertDialogCancel>
          <Button
            variant={destrutivo ? "destructive" : "default"}
            disabled={ocupado}
            onClick={aoConfirmar}
          >
            {ocupado && <Loader2 aria-hidden className="animate-spin" />}
            {textoConfirmar}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
