import { AlertTriangle } from "lucide-react";
import { isRouteErrorResponse, Link, useRouteError } from "react-router-dom";
import { buttonVariants } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/backend";

/** Erro inesperado de renderização ou rota inexistente: mensagem em pt-BR e volta ao início. */
export function ErroGlobal() {
  const erro = useRouteError();
  const naoEncontrada = erro === undefined || (isRouteErrorResponse(erro) && erro.status === 404);
  return (
    <div role="alert" className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6">
      <AlertTriangle aria-hidden className="size-8 text-perigo" />
      <h1 className="text-lg font-semibold">
        {naoEncontrada ? "Página não encontrada" : "Algo deu errado nesta tela"}
      </h1>
      {!naoEncontrada && (
        <p className="max-w-md text-center text-sm text-muted-foreground">{mensagemDeErro(erro)}</p>
      )}
      <Link to="/" className={buttonVariants({ variant: "outline" })}>
        Voltar ao Dashboard
      </Link>
    </div>
  );
}
