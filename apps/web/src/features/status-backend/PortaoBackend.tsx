import { AlertTriangle, Loader2, RotateCcw } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { criarClienteApi, mensagemDeErro } from "@/lib/backend";
import { ContextoClienteApi } from "@/lib/cliente-api";
import { useConexaoBackend, useReiniciarBackend } from "./consultas";

/**
 * Só libera a UI depois que o backend respondeu ao /health.
 * Mostra carregamento enquanto inicia e erro claro (com nova tentativa) se falhar.
 */
export function PortaoBackend({ children }: { children: ReactNode }) {
  const conexao = useConexaoBackend();
  const reiniciar = useReiniciarBackend();
  const cliente = useMemo(
    () => (conexao.data ? criarClienteApi(conexao.data) : null),
    [conexao.data],
  );

  if (conexao.isPending || reiniciar.isPending) {
    return (
      <TelaCentral>
        <Loader2 aria-hidden className="size-8 animate-spin text-muted-foreground" />
        <p role="status" className="text-muted-foreground">
          Iniciando o serviço interno…
        </p>
      </TelaCentral>
    );
  }

  if (conexao.isError || !cliente) {
    return (
      <TelaCentral>
        <AlertTriangle aria-hidden className="size-8 text-perigo" />
        <h1 className="text-lg font-semibold">Não foi possível iniciar o serviço interno</h1>
        <p role="alert" className="max-w-md text-center text-sm text-muted-foreground">
          {mensagemDeErro(conexao.error)}
        </p>
        {reiniciar.isError && (
          <p className="max-w-md text-center text-sm text-perigo">
            {mensagemDeErro(reiniciar.error)}
          </p>
        )}
        <Button
          onClick={() => {
            reiniciar.mutate();
          }}
        >
          <RotateCcw aria-hidden />
          Tentar novamente
        </Button>
      </TelaCentral>
    );
  }

  return (
    <ContextoClienteApi.Provider value={{ cliente, conexao: conexao.data }}>
      {children}
    </ContextoClienteApi.Provider>
  );
}

function TelaCentral({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
      {children}
    </main>
  );
}
