import { Select } from "@/components/ui/input";
import { useAnaliseStore, useInstituicoes } from "@/lib/consultas-comuns";

/**
 * Análise Geral (todas as instituições consolidadas) ou por Instituição.
 * A escolha vale para Dashboard e Carteira até o app ser fechado.
 */
export function SeletorAnalise() {
  const instituicoes = useInstituicoes();
  const instituicaoId = useAnaliseStore((s) => s.instituicaoId);
  const definir = useAnaliseStore((s) => s.definirInstituicao);
  const existe = instituicoes.data?.some((i) => i.id === instituicaoId) ?? false;
  const valor = instituicaoId !== null && existe ? String(instituicaoId) : "";

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="whitespace-nowrap text-muted-foreground">Análise</span>
      <Select
        className="w-56"
        value={valor}
        disabled={instituicoes.isPending}
        onChange={(e) => {
          definir(e.target.value ? Number(e.target.value) : null);
        }}
      >
        <option value="">Análise Geral</option>
        {instituicoes.data?.map((i) => (
          <option key={i.id} value={i.id}>
            {i.nome}
          </option>
        ))}
      </Select>
    </label>
  );
}
