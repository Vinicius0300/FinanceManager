import { Outlet } from "react-router-dom";
import { SeletorTema } from "@/components/SeletorTema";

/** Casca provisória; navegação entre telas e visual final chegam nas próximas partes. */
export function LayoutApp() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <span className="text-lg font-semibold">Finanças</span>
        <SeletorTema />
      </header>
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
