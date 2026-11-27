import { AlertTriangle, ArrowDownRight, ArrowUpRight, Info } from "lucide-react";
import { IndicadorDefasado } from "@/components/IndicadorDefasado";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { nomeDoTipo, type TipoAtivo } from "@/lib/consultas-comuns";
import { absoluto } from "@/lib/decimal";
import { casasDeExibicao, formatarMoeda, formatarQuantidade } from "@/lib/formatacao";
import type { AtivoPlano, ClassePlano, Plano } from "./consultas";

export const AVISO_IR = "Vendas podem gerar imposto de renda. O app não calcula o IR.";
export const FRASE_INFORMATIVA =
  "Sugestão informativa com base nas suas metas. O app nunca executa ordens.";

/**
 * "Como dividir o aporte" (só compras) ou "Rebalanceamento completo" (compras e vendas).
 * A sugestão desce até o ativo quando a classe tem pesos; nas vendas por ativo mostra a
 * quantidade aproximada e o lucro estimado, com o aviso de IR.
 */
export function PlanoAporte({
  plano,
  tipos,
}: {
  plano: Plano;
  tipos: readonly TipoAtivo[] | undefined;
}) {
  const comAcao = plano.classes.filter((c) => c.acao !== "manter");
  const manter = plano.classes.filter((c) => c.acao === "manter");
  const completo = plano.modo === "completo";
  return (
    <div className="flex flex-col gap-3">
      {comAcao.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {completo
            ? "Nada a comprar ou vender: a carteira já está nas metas."
            : "Nenhum aporte a dividir. Informe um valor no campo Aporte."}
        </p>
      ) : (
        <ul className="flex flex-col divide-y" aria-label="Sugestões por classe">
          {comAcao.map((classe) => (
            <LinhaClasse
              key={classe.tipo_ativo}
              classe={classe}
              nome={nomeDoTipo(tipos, classe.tipo_ativo)}
            />
          ))}
        </ul>
      )}
      {manter.length > 0 && comAcao.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Manter: {manter.map((c) => nomeDoTipo(tipos, c.tipo_ativo)).join(", ")}.
        </p>
      )}
      {completo && (
        <p
          role="note"
          className="flex items-start gap-2 rounded-md border border-aviso/40 bg-aviso/10 px-3 py-2 text-sm"
        >
          <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-aviso-texto" />
          {AVISO_IR}
        </p>
      )}
      {plano.avisos.map((aviso) => (
        <p key={aviso} className="text-xs text-aviso-texto">
          {aviso}
        </p>
      ))}
      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        {FRASE_INFORMATIVA}
      </p>
    </div>
  );
}

function LinhaClasse({ classe, nome }: { classe: ClassePlano; nome: string }) {
  const comprar = classe.acao === "aportar";
  const Icone = comprar ? ArrowUpRight : ArrowDownRight;
  const ativos = classe.usa_pesos ? classe.ativos.filter((a) => a.acao !== "manter") : [];
  return (
    <li className="py-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="flex items-center gap-1.5 font-semibold">
          <Icone
            aria-hidden
            className={comprar ? "size-4 text-positivo" : "size-4 text-negativo"}
          />
          {comprar ? `Aportar em ${nome}` : `Reduzir ${nome}`}
        </span>
        <span className="tabular font-semibold">
          {formatarMoeda(absoluto(classe.sugestao ?? "0"))}
        </span>
      </div>
      {!classe.usa_pesos && (
        <p className="pl-5.5 text-xs text-muted-foreground">
          {comprar
            ? "Você escolhe o ativo da classe."
            : "Você escolhe o que vender na classe (dê pesos aos ativos para ver o lucro estimado)."}
        </p>
      )}
      {ativos.length > 0 && (
        <ul className="mt-1 flex flex-col gap-1 pl-5.5" aria-label={`Ativos de ${nome}`}>
          {ativos.map((ativo) => (
            <LinhaAtivo key={ativo.ativo_id} ativo={ativo} />
          ))}
        </ul>
      )}
    </li>
  );
}

function LinhaAtivo({ ativo }: { ativo: AtivoPlano }) {
  const vender = ativo.acao === "vender";
  const rotulo = ativo.simbolo ?? ativo.nome;
  return (
    <li className="text-[0.8125rem]">
      <div className="flex flex-wrap items-center justify-between gap-x-3">
        <span>
          <span className="font-medium">{rotulo}</span>{" "}
          <span className="text-muted-foreground">{vender ? "vender" : "comprar"}</span>{" "}
          <IndicadorDefasado defasado={ativo.defasado} aviso={ativo.aviso} />
        </span>
        <span className="tabular">{formatarMoeda(absoluto(ativo.sugestao ?? "0"))}</span>
      </div>
      {vender && (ativo.quantidade_estimada !== null || ativo.lucro_estimado !== null) && (
        <p className="text-xs text-muted-foreground">
          {ativo.quantidade_estimada !== null && (
            <>
              ≈{" "}
              {formatarQuantidade(ativo.quantidade_estimada, {
                maximo: casasDeExibicao(ativo.quantidade_estimada, 3),
              })}{" "}
              unidades ·{" "}
            </>
          )}
          lucro estimado <ValorFinanceiro valor={ativo.lucro_estimado} seta={false} />
        </p>
      )}
      {ativo.aviso && <p className="text-xs text-aviso-texto">{ativo.aviso}</p>}
    </li>
  );
}
