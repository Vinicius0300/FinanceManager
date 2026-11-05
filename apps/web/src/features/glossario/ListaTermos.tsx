import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { CATEGORIAS } from "./dominio/categorias";
import { rotaDoTermo } from "./dominio/links";
import type { Termo } from "./dominio/termo";
import { MarcadorCategoria } from "./Verbete";

/**
 * Lista de termos agrupada por categoria: o caminho pelo teclado (Tab entre os links) e
 * para leitores de tela, já que o grafo é um desenho em canvas. Sem busca, segue a ordem
 * do índice; com busca, os grupos mantêm a ordem de relevância do resultado.
 */
export function ListaTermos({ termos }: { termos: readonly Termo[] }) {
  const grupos = CATEGORIAS.map((c) => ({
    ...c,
    termos: termos.filter((t) => t.categoria === c.id),
  })).filter((g) => g.termos.length > 0);

  return (
    <nav
      aria-label="Termos do glossário"
      className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3"
    >
      {grupos.map((grupo) => (
        <section key={grupo.id} aria-labelledby={`grupo-${grupo.id}`} className="min-w-0">
          <h3
            id={`grupo-${grupo.id}`}
            className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground"
          >
            <MarcadorCategoria categoria={grupo.id} />
            {grupo.rotulo}
          </h3>
          <ul className="space-y-0.5">
            {grupo.termos.map((t) => (
              <li key={t.slug}>
                <NavLink
                  to={rotaDoTermo(t.slug)}
                  title={t.resumo}
                  className={({ isActive }) =>
                    cn(
                      "block truncate rounded-md px-2 py-1 text-sm transition-colors outline-none hover:bg-accent hover:text-accent-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      isActive && "bg-accent font-semibold text-accent-foreground",
                    )
                  }
                >
                  {t.titulo}
                </NavLink>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </nav>
  );
}
