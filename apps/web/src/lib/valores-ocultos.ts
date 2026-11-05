import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Modo privacidade: oculta na tela os valores do usuário (saldos, patrimônio, aportes,
 * compras, receitas, despesas, quantidades). Percentuais e cotações de mercado continuam
 * visíveis. A preferência fica salva entre aberturas do app (como o tema).
 *
 * Os formatadores de `lib/formatacao` consultam `valoresOcultos()` e devolvem a máscara;
 * para a tela redesenhar ao alternar, cada tela (e todo componente que guarda texto
 * formatado em `useMemo`) assina o store com `useValoresOcultos()`.
 */
export const MASCARA_VALOR = "•••••";

interface EstadoValoresOcultos {
  ocultos: boolean;
  alternar: () => void;
  definir: (ocultos: boolean) => void;
}

export const useValoresOcultosStore = create<EstadoValoresOcultos>()(
  persist(
    (set) => ({
      ocultos: false,
      alternar: () => {
        set((estado) => ({ ocultos: !estado.ocultos }));
      },
      definir: (ocultos) => {
        set({ ocultos });
      },
    }),
    {
      name: "financas-valores-ocultos",
      version: 1,
      partialize: (estado) => ({ ocultos: estado.ocultos }),
    },
  ),
);

/** Leitura fora do React (formatadores). */
export function valoresOcultos(): boolean {
  return useValoresOcultosStore.getState().ocultos;
}

/** Assina o modo privacidade: o componente redesenha quando ele muda. */
export function useValoresOcultos(): boolean {
  return useValoresOcultosStore((s) => s.ocultos);
}
