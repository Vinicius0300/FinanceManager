import { GraphChart } from "echarts/charts";
import { use as registrarModulos } from "echarts/core";
import { LabelLayout } from "echarts/features";
import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { GraficoECharts, type EventoCliqueGrafico } from "@/components/graficos/GraficoECharts";
import { useCoresTema } from "@/theme/cores";
import type { IndiceGlossario } from "./dominio/indice";
import { ajustarProporcao, calcularPosicoes } from "./dominio/layout";
import { rotaDoTermo } from "./dominio/links";
import { opcoesGrafo } from "./grafo";

// O tipo "graph" e o layout de rótulos (esconder nomes sobrepostos) só são registrados aqui:
// o módulo do glossário é carregado sob demanda e as outras telas não pagam por eles.
registrarModulos([GraphChart, LabelLayout]);

/**
 * Largura ÷ altura do desenho. A área do grafo ocupa a largura da tela (~900 a 1.200 px)
 * com 520 px de altura; 1,9 aproveita bem essa faixa.
 */
const PROPORCAO_DESENHO = 1.9;

/**
 * Grafo de conhecimento: bolinhas coloridas pela categoria, tamanho pelo número de
 * ligações, clique abre o verbete. As posições são calculadas uma vez para o glossário
 * inteiro: o filtro de categoria só esconde nós, sem embaralhar o desenho.
 */
export function GrafoGlossario({
  indice,
  visiveis,
  selecionado,
  altura = 520,
}: {
  indice: IndiceGlossario;
  visiveis: readonly string[];
  selecionado: string | null;
  altura?: number;
}) {
  const navegar = useNavigate();
  const cores = useCoresTema();

  const posicoes = useMemo(
    () =>
      ajustarProporcao(
        calcularPosicoes(
          indice.termos.map((t) => t.slug),
          indice.arestas,
        ),
        PROPORCAO_DESENHO,
      ),
    [indice],
  );

  const opcoes = useMemo(
    () => opcoesGrafo({ indice, visiveis, posicoes, selecionado, cores }),
    [indice, visiveis, posicoes, selecionado, cores],
  );

  const aoClicar = useCallback(
    (evento: EventoCliqueGrafico) => {
      const dado = evento.data as { id?: unknown } | undefined;
      if (evento.dataType === "node" && typeof dado?.id === "string") {
        void navegar(rotaDoTermo(dado.id));
      }
    },
    [navegar],
  );

  const rotulo = `Grafo do glossário: ${String(visiveis.length)} termos e as ligações entre eles. Para navegar pelo teclado, escolha a visualização Lista de termos.`;

  return <GraficoECharts opcoes={opcoes} rotulo={rotulo} altura={altura} aoClicar={aoClicar} />;
}
