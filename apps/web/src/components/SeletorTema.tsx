import { Moon, Sun } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { useTemaStore } from "@/theme/tema";

/** Switch de tema: ligado = escuro, desligado = claro. */
export function SeletorTema() {
  const tema = useTemaStore((s) => s.tema);
  const alternarTema = useTemaStore((s) => s.alternarTema);
  const escuro = tema === "escuro";

  return (
    <div className="flex items-center gap-2">
      <Sun aria-hidden className="size-4 text-muted-foreground" />
      <Switch
        checked={escuro}
        onCheckedChange={alternarTema}
        aria-label="Modo escuro"
        title={escuro ? "Modo escuro ativo" : "Modo claro ativo"}
      />
      <Moon aria-hidden className="size-4 text-muted-foreground" />
    </div>
  );
}
