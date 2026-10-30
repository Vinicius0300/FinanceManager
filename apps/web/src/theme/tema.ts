import { useEffect } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Tema = "claro" | "escuro";

/** Tema usado na primeira abertura (e se a preferência salva for inválida). */
export const TEMA_PADRAO: Tema = "escuro";

interface EstadoTema {
  tema: Tema;
  definirTema: (tema: Tema) => void;
  alternarTema: () => void;
}

export const useTemaStore = create<EstadoTema>()(
  persist(
    (set) => ({
      tema: TEMA_PADRAO,
      definirTema: (tema) => {
        set({ tema });
      },
      alternarTema: () => {
        set((estado) => ({ tema: estado.tema === "escuro" ? "claro" : "escuro" }));
      },
    }),
    {
      name: "financas-tema",
      version: 1,
      partialize: (estado) => ({ tema: estado.tema }),
      // v0 guardava { preferencia: "sistema" | "claro" | "escuro" }; "sistema" vira o padrão.
      migrate: (salvo) => {
        const antigo = (salvo ?? {}) as { preferencia?: unknown };
        return { tema: antigo.preferencia === "claro" ? "claro" : TEMA_PADRAO };
      },
    },
  ),
);

/** Coloca (ou tira) a classe `dark` do <html>. */
export function aplicarClasseTema(tema: Tema): void {
  document.documentElement.classList.toggle("dark", tema === "escuro");
}

// A classe muda junto com o estado (antes de o React redesenhar): quem lê as variáveis CSS
// durante a renderização (cores dos gráficos) já enxerga o tema novo.
useTemaStore.subscribe((estado) => {
  aplicarClasseTema(estado.tema);
});

/** Garante a classe `dark` do tema salvo ao abrir o app (o store já a mantém depois). */
export function useAplicarTema(): void {
  const tema = useTemaStore((s) => s.tema);

  useEffect(() => {
    aplicarClasseTema(tema);
  }, [tema]);
}
