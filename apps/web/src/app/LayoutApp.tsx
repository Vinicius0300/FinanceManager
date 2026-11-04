import { NavLink, Outlet } from "react-router-dom";
import { Marca } from "@/components/Marca";
import { useAtualizacaoTempoReal } from "@/features/tempo-real/atualizacao";
import { cn } from "@/lib/utils";
import { BarraSuperior } from "./BarraSuperior";
import { NAVEGACAO } from "./navegacao";

/**
 * Casca do app: navegação lateral (azul-marinho), topo global e a área da tela.
 * Em janelas estreitas (< 1024 px) a lateral mostra só os ícones (o nome fica no `title`
 * e para leitores de tela), para sobrar espaço às tabelas e gráficos.
 */
export function LayoutApp() {
  useAtualizacaoTempoReal();
  return (
    <div className="flex min-h-screen">
      {/* A coluna estica até o fim da página (fundo contínuo); o menu fica fixo no topo. */}
      <div className="w-16 shrink-0 bg-lateral lg:w-[13rem]">
        <nav
          aria-label="Navegação principal"
          className="sticky top-0 flex h-screen flex-col gap-1 px-2.5 py-5 text-lateral-foreground lg:px-3.5"
        >
          <span className="mb-5 flex items-center justify-center gap-2.5 px-1 text-[1.05rem] font-bold text-lateral-ativo lg:justify-start dark:text-foreground">
            <Marca />
            <span className="hidden lg:inline">Finanças</span>
          </span>
          {NAVEGACAO.map(({ para, rotulo, icone: Icone }) => (
            <NavLink
              key={para}
              to={para}
              end={para === "/"}
              title={rotulo}
              className={({ isActive }) =>
                cn(
                  "flex items-center justify-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition-colors hover:bg-lateral-foreground/10 lg:justify-start",
                  isActive &&
                    "bg-lateral-ativo font-semibold text-lateral-ativo-foreground hover:bg-lateral-ativo",
                )
              }
            >
              <Icone aria-hidden className="size-4 shrink-0" />
              <span className="sr-only lg:not-sr-only">{rotulo}</span>
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <BarraSuperior />
        <main className="min-w-0 flex-1 px-5 py-5 xl:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
