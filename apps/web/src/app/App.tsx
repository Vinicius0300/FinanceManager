import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { PortaoBackend } from "@/features/status-backend/PortaoBackend";
import { TelaStatusBackend } from "@/features/status-backend/TelaStatusBackend";
import { useAplicarTema } from "@/theme/tema";
import { LayoutApp } from "./LayoutApp";

const roteador = createBrowserRouter([
  {
    path: "/",
    element: <LayoutApp />,
    children: [{ index: true, element: <TelaStatusBackend /> }],
  },
]);

export function App() {
  useAplicarTema();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { refetchOnWindowFocus: false } },
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
