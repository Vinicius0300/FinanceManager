import type { RouteObject } from "react-router-dom";
import { TelaCarteira } from "@/features/carteira/TelaCarteira";
import { TelaConfiguracoes } from "@/features/configuracoes/TelaConfiguracoes";
import { TelaDashboard } from "@/features/dashboard/TelaDashboard";
import { TelaMovimentacoes } from "@/features/movimentacoes/TelaMovimentacoes";
import { TelaReceitasDespesas } from "@/features/receitas-despesas/TelaReceitasDespesas";
import { ErroGlobal } from "./ErroGlobal";
import { LayoutApp } from "./LayoutApp";

export const ROTAS: RouteObject[] = [
  {
    path: "/",
    element: <LayoutApp />,
    errorElement: <ErroGlobal />,
    children: [
      { index: true, element: <TelaDashboard /> },
      { path: "carteira", element: <TelaCarteira /> },
      { path: "movimentacoes", element: <TelaMovimentacoes /> },
      { path: "receitas-despesas", element: <TelaReceitasDespesas /> },
      { path: "configuracoes", element: <TelaConfiguracoes /> },
      { path: "*", element: <ErroGlobal /> },
    ],
  },
];
