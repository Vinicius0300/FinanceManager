import { createContext, useContext } from "react";
import type { ClienteApi, ConexaoBackend } from "@/lib/backend";

export interface ValorClienteApi {
  cliente: ClienteApi;
  conexao: ConexaoBackend;
}

/** Preenchido pelo PortaoBackend depois que o backend respondeu ao /health. */
export const ContextoClienteApi = createContext<ValorClienteApi | null>(null);

/** Cliente tipado da API (gerado do OpenAPI) e dados da conexão atual. */
export function useClienteApi(): ValorClienteApi {
  const valor = useContext(ContextoClienteApi);
  if (!valor) throw new Error("useClienteApi precisa estar dentro do PortaoBackend.");
  return valor;
}
