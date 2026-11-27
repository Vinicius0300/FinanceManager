import {
  ArrowLeftRight,
  BookOpen,
  LayoutDashboard,
  type LucideIcon,
  Scale,
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
  { para: "/rebalanceamento", rotulo: "Rebalanceamento", icone: Scale },
  { para: "/movimentacoes", rotulo: "Movimentações", icone: ArrowLeftRight },
  { para: "/receitas-despesas", rotulo: "Receitas e Despesas", icone: WalletCards },
  { para: "/glossario", rotulo: "Glossário", icone: BookOpen },
  { para: "/configuracoes", rotulo: "Configurações", icone: Settings },
];
