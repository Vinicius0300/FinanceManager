import { NavLink, Outlet } from "react-router-dom";
import { SeletorTema } from "@/components/SeletorTema";
import { useAtualizacaoTempoReal, useEstadoAtualizacao } from "@/features/tempo-real/atualizacao";
import { formatarDataHora } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import { NAVEGACAO } from "./navegacao";

/** Casca do app: navegação lateral (azul-marinho), topo com o tema e a área da tela. */
export function LayoutApp() {
  useAtualizacaoTempoReal();
  return (
    <div className="flex min-h-screen">
      <nav
        aria-label="Navegação principal"
        className="flex w-56 shrink-0 flex-col gap-1 bg-lateral px-3 py-5 text-lateral-foreground"
      >
        <span className="px-3 pb-5 text-lg font-bold">Finanças</span>
        {NAVEGACAO.map(({ para, rotulo, icone: Icone }) => (
          <NavLink
            key={para}
            to={para}
            end={para === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-full px-3 py-2 text-sm transition-colors hover:bg-lateral-foreground/10",
                isActive &&
                  "bg-lateral-ativo font-semibold text-lateral-ativo-foreground hover:bg-lateral-ativo",
              )
            }
          >
            <Icone aria-hidden className="size-4" />
            {rotulo}
          </NavLink>
        ))}
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-4 border-b px-6 py-2.5">
          <StatusAtualizacao />
          <SeletorTema />
        </header>
        <main className="min-w-0 flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

/** Última atualização automática concluída (vem do stream SSE). */
function StatusAtualizacao() {
  const ultimoFim = useEstadoAtualizacao((s) => s.ultimoFim);
  const erros = useEstadoAtualizacao((s) => s.ultimosErros);
  const mensagem = useEstadoAtualizacao((s) => s.ultimaMensagemErro);
  if (!ultimoFim) return null;
  return (
    <p className="text-xs text-muted-foreground" aria-live="polite">
      Cotações atualizadas em {formatarDataHora(ultimoFim)}
      {erros > 0 && (
        <span className="text-aviso-texto" title={mensagem ?? undefined}>
          {" "}
          · {erros} {erros === 1 ? "falha" : "falhas"}
        </span>
      )}
    </p>
  );
}
