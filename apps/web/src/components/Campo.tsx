import { useId, type ReactElement, type ReactNode } from "react";
import { cloneElement, isValidElement } from "react";
import { Label } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Campo de formulário: rótulo ligado ao controle (acessibilidade), ajuda e erro em pt-BR.
 * O controle filho recebe `id`, `aria-invalid` e `aria-describedby` automaticamente.
 */
export function Campo({
  rotulo,
  erro,
  ajuda,
  obrigatorio = false,
  className,
  children,
}: {
  rotulo: string;
  erro?: string | undefined;
  ajuda?: ReactNode;
  obrigatorio?: boolean;
  className?: string;
  children: ReactElement<Record<string, unknown>>;
}) {
  const id = useId();
  const idAjuda = `${id}-ajuda`;
  const idErro = `${id}-erro`;
  const descritores = [ajuda ? idAjuda : null, erro ? idErro : null].filter(Boolean).join(" ");
  const controle = isValidElement(children)
    ? cloneElement(children, {
        id,
        "aria-invalid": erro ? true : undefined,
        "aria-describedby": descritores || undefined,
      })
    : children;
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <Label htmlFor={id}>
        {rotulo}
        {obrigatorio && (
          <span aria-hidden className="text-muted-foreground">
            {" "}
            *
          </span>
        )}
      </Label>
      {controle}
      {ajuda && (
        <p id={idAjuda} className="text-xs text-muted-foreground">
          {ajuda}
        </p>
      )}
      {erro && (
        <p id={idErro} role="alert" className="text-xs text-negativo">
          {erro}
        </p>
      )}
    </div>
  );
}
