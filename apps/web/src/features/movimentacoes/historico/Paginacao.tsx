import { ChevronLeft, ChevronRight } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { TAMANHOS_PAGINA, totalDePaginas, type TamanhoPagina } from "./filtros";

/**
 * Rodapé de paginação do histórico (Parte 9): "Mostrar [10|25|50|100] <itens> por página",
 * faixa exibida, "Página X de Y" e Anterior/Próxima. Usado nas duas visões.
 */
export function Paginacao({
  total,
  pagina,
  tamanho,
  unidade,
  aoPaginar,
  aoMudarTamanho,
}: {
  total: number;
  pagina: number;
  tamanho: TamanhoPagina;
  unidade: { singular: string; plural: string };
  aoPaginar: (pagina: number) => void;
  aoMudarTamanho: (tamanho: TamanhoPagina) => void;
}) {
  const id = useId();
  if (total === 0) return null;
  const paginas = totalDePaginas(total, tamanho);
  const inicio = (pagina - 1) * tamanho + 1;
  const fim = Math.min(total, pagina * tamanho);
  const nome = total === 1 ? unidade.singular : unidade.plural;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-3 text-sm text-muted-foreground">
      <div className="flex items-center gap-2">
        <label htmlFor={`${id}-tamanho`}>Mostrar</label>
        <Select
          id={`${id}-tamanho`}
          className="h-8 w-auto"
          value={tamanho}
          onChange={(e) => {
            aoMudarTamanho(Number(e.target.value) as TamanhoPagina);
          }}
        >
          {TAMANHOS_PAGINA.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <span>{unidade.plural} por página</span>
      </div>
      <span className="flex-1" />
      <span className="tabular" aria-live="polite">
        {inicio.toLocaleString("pt-BR")}–{fim.toLocaleString("pt-BR")} de{" "}
        {total.toLocaleString("pt-BR")} {nome}
      </span>
      <nav aria-label="Paginação" className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={pagina <= 1}
          onClick={() => {
            aoPaginar(pagina - 1);
          }}
        >
          <ChevronLeft aria-hidden />
          Anterior
        </Button>
        <span className="tabular">
          Página {pagina} de {paginas}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={pagina >= paginas}
          onClick={() => {
            aoPaginar(pagina + 1);
          }}
        >
          Próxima
          <ChevronRight aria-hidden />
        </Button>
      </nav>
    </div>
  );
}
