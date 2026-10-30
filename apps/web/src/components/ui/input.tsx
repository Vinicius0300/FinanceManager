import { forwardRef, type ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";

/*
 * Controles de formulário com `forwardRef`: no React 18 o `ref` não chega como prop, e o
 * React Hook Form precisa dele (`register`) para preencher valores iniciais e resetar.
 */

const CLASSE_CAMPO =
  "h-9 w-full min-w-0 rounded-md border border-input bg-card px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20";

const Input = forwardRef<HTMLInputElement, ComponentPropsWithoutRef<"input">>(
  ({ className, type, ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      data-slot="input"
      className={cn(CLASSE_CAMPO, className)}
      {...props}
    />
  ),
);
Input.displayName = "Input";

const Textarea = forwardRef<HTMLTextAreaElement, ComponentPropsWithoutRef<"textarea">>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      data-slot="textarea"
      className={cn(CLASSE_CAMPO, "h-auto min-h-16 py-2", className)}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

/**
 * Seletor nativo estilizado pelos tokens. Preferido ao Select do Radix: acessível por
 * padrão (teclado e leitor de tela do Windows), sem portal e simples de testar.
 */
const Select = forwardRef<HTMLSelectElement, ComponentPropsWithoutRef<"select">>(
  ({ className, ...props }, ref) => (
    <select
      ref={ref}
      data-slot="select"
      className={cn(CLASSE_CAMPO, "pr-8", className)}
      {...props}
    />
  ),
);
Select.displayName = "Select";

const Checkbox = forwardRef<HTMLInputElement, Omit<ComponentPropsWithoutRef<"input">, "type">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      type="checkbox"
      data-slot="checkbox"
      className={cn("size-4 shrink-0 rounded border-input accent-primary", className)}
      {...props}
    />
  ),
);
Checkbox.displayName = "Checkbox";

function Label({ className, ...props }: ComponentPropsWithoutRef<"label">) {
  return (
    <label
      data-slot="label"
      className={cn("text-sm leading-none font-medium select-none", className)}
      {...props}
    />
  );
}

export { Checkbox, Input, Label, Select, Textarea };
