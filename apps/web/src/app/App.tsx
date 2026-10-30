import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { PortaoBackend } from "@/features/status-backend/PortaoBackend";
import { useAplicarTema } from "@/theme/tema";
import { ROTAS } from "./rotas";

const roteador = createBrowserRouter(ROTAS);

export function App() {
  useAplicarTema();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 15_000 },
          mutations: { retry: false },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <PortaoBackend>
        <RouterProvider router={roteador} />
      </PortaoBackend>
    </QueryClientProvider>
  );
}
