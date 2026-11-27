import type { RouteObject } from "react-router-dom";
import { TelaCarteira } from "@/features/carteira/TelaCarteira";
import { TelaConfiguracoes } from "@/features/configuracoes/TelaConfiguracoes";
import { TelaDashboard } from "@/features/dashboard/TelaDashboard";
import { TelaMovimentacoes } from "@/features/movimentacoes/TelaMovimentacoes";
import { TelaReceitasDespesas } from "@/features/receitas-despesas/TelaReceitasDespesas";
import { TelaRebalanceamento } from "@/features/rebalanceamento/TelaRebalanceamento";
import { ErroGlobal } from "./ErroGlobal";
import { GlossarioSobDemanda } from "./GlossarioSobDemanda";
import { LayoutApp } from "./LayoutApp";

export const ROTAS: RouteObject[] = [
  {
    path: "/",
    element: <LayoutApp />,
    errorElement: <ErroGlobal />,
    children: [
      { index: true, element: <TelaDashboard /> },
      { path: "carteira", element: <TelaCarteira /> },
      { path: "rebalanceamento", element: <TelaRebalanceamento /> },
      { path: "movimentacoes", element: <TelaMovimentacoes /> },
      { path: "receitas-despesas", element: <TelaReceitasDespesas /> },
      { path: "glossario/:termo?", element: <GlossarioSobDemanda /> },
      { path: "configuracoes", element: <TelaConfiguracoes /> },
      { path: "*", element: <ErroGlobal /> },
    ],
  },
];
