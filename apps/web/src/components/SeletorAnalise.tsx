import { useState } from "react";
import { Segmentos } from "@/components/Segmentos";
import { Select } from "@/components/ui/input";
import { useAnaliseStore, useInstituicoes } from "@/lib/consultas-comuns";

type Modo = "geral" | "instituicao";

const OPCOES = [
  { valor: "geral", rotulo: "Análise Geral" },
  { valor: "instituicao", rotulo: "Por Instituição" },
] as const;

/**
 * Análise Geral (todas as instituições consolidadas) ou por Instituição, em segmentos.
 * Em "Por Instituição" aparece a lista de instituições; ao entrar nela, a primeira já vem
 * escolhida. A escolha vale para Dashboard e Carteira até o app ser fechado.
 */
export function SeletorAnalise() {
  const instituicoes = useInstituicoes();
  const instituicaoId = useAnaliseStore((s) => s.instituicaoId);
  const definir = useAnaliseStore((s) => s.definirInstituicao);
  const existe = instituicoes.data?.some((i) => i.id === instituicaoId) ?? false;
  const selecionada = instituicaoId !== null && existe;
  // "Por Instituição" sem instituição escolhida (ex.: nenhuma cadastrada) mostra só o aviso.
  const [semInstituicao, setSemInstituicao] = useState(false);
  const modo: Modo = selecionada || semInstituicao ? "instituicao" : "geral";
  const lista = instituicoes.data ?? [];

  const mudarModo = (novo: Modo) => {
    if (novo === "geral") {
      setSemInstituicao(false);
      definir(null);
      return;
    }
    const primeira = lista[0];
    if (primeira) definir(primeira.id);
    else setSemInstituicao(true);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Segmentos rotulo="Tipo de análise" opcoes={OPCOES} valor={modo} aoMudar={mudarModo} />
      {modo === "instituicao" &&
        (lista.length > 0 ? (
          <label className="flex items-center gap-2 text-sm">
            <span className="sr-only">Instituição</span>
            <Select
              className="h-8 w-44"
              value={selecionada ? String(instituicaoId) : ""}
              disabled={instituicoes.isPending}
              onChange={(e) => {
                definir(Number(e.target.value));
              }}
            >
              {lista.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.nome}
                </option>
              ))}
            </Select>
          </label>
        ) : (
          <span className="text-xs text-muted-foreground">Nenhuma instituição cadastrada</span>
        ))}
    </div>
  );
}
