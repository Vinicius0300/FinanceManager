import {
  ArrowLeftRight,
  LayoutDashboard,
  type LucideIcon,
  Settings,
  Wallet,
  WalletCards,
} from "lucide-react";

export interface ItemNavegacao {
  para: string;
  rotulo: string;
  icone: LucideIcon;
}

export const NAVEGACAO: readonly ItemNavegacao[] = [
  { para: "/", rotulo: "Dashboard", icone: LayoutDashboard },
  { para: "/carteira", rotulo: "Carteira", icone: Wallet },
  { para: "/movimentacoes", rotulo: "Movimentações", icone: ArrowLeftRight },
  { para: "/receitas-despesas", rotulo: "Receitas e Despesas", icone: WalletCards },
  { para: "/configuracoes", rotulo: "Configurações", icone: Settings },
];
