import { lazy, Suspense } from "react";
import { Carregando } from "@/components/Estados";

// O glossário (conteúdo, grafo e Markdown) fica num pedaço separado do build e só é
// baixado quando a aba é aberta, sem pesar na abertura do app.
const TelaGlossario = lazy(() =>
  import("@/features/glossario/TelaGlossario").then((m) => ({ default: m.TelaGlossario })),
);

export function GlossarioSobDemanda() {
  return (
    <Suspense fallback={<Carregando texto="Abrindo o glossário…" />}>
      <TelaGlossario />
    </Suspense>
  );
}
