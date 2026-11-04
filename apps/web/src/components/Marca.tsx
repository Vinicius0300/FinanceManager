import { cn } from "@/lib/utils";

/**
 * Marca do app (o mesmo desenho do ícone em `apps/desktop/icone.svg`): quadrado violeta com
 * três barras crescentes e a linha de tendência. Cores pelos tokens (`--primary` e
 * `--primary-foreground`), então acompanha o tema.
 */
export function Marca({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-7 shrink-0", className)}>
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <g className="fill-primary-foreground">
        <rect x="7" y="18" width="4.5" height="7" rx="1.2" />
        <rect x="13.75" y="14" width="4.5" height="11" rx="1.2" />
        <rect x="20.5" y="10" width="4.5" height="15" rx="1.2" />
      </g>
      <path
        d="M7 13.5 13.5 9.5l4 2.5L25 6.5"
        fill="none"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-primary-foreground"
      />
    </svg>
  );
}
