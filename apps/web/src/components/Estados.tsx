import { AlertTriangle, Inbox, Loader2, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { mensagemDeErro } from "@/lib/backend";
import { cn } from "@/lib/utils";

/** Carregamento de uma área (nunca bloqueia o resto da tela). */
export function Carregando({
  texto = "Carregando…",
  className,
}: {
  texto?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground",
        className,
      )}
    >
      <Loader2 aria-hidden className="size-4 animate-spin" />
      {texto}
    </div>
  );
}

/** Estado vazio com uma ação opcional (ex.: "Cadastrar ativo", "Limpar filtros"). */
export function EstadoVazio({
  titulo,
  descricao,
  acao,
  className,
}: {
  titulo: string;
  descricao?: string;
  acao?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-2 py-10 text-center", className)}>
      <Inbox aria-hidden className="size-8 text-muted-foreground" />
      <p className="font-medium">{titulo}</p>
      {descricao && <p className="max-w-md text-sm text-muted-foreground">{descricao}</p>}
      {acao}
    </div>
  );
}

/** Erro compreensível em pt-BR, com "Tentar novamente" quando houver como refazer. */
export function EstadoErro({
  erro,
  aoTentarNovamente,
  className,
}: {
  erro: unknown;
  aoTentarNovamente?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center gap-2 py-8 text-center", className)}
    >
      <AlertTriangle aria-hidden className="size-6 text-perigo" />
      <p className="max-w-md text-sm">{mensagemDeErro(erro)}</p>
      {aoTentarNovamente && (
        <Button variant="outline" size="sm" onClick={aoTentarNovamente}>
          <RotateCcw aria-hidden />
          Tentar novamente
        </Button>
      )}
    </div>
  );
}

/** Mensagem de erro curta dentro de formulários e diálogos. */
export function MensagemErro({ erro }: { erro: unknown }) {
  if (!erro) return null;
  return (
    <p role="alert" className="rounded-md border border-perigo/40 bg-perigo/10 px-3 py-2 text-sm">
      {mensagemDeErro(erro)}
    </p>
  );
}
