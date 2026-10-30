import { Pencil, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import {} from "@/lib/api";
import {} from "@/lib/cliente-api";
import {
  nomeDoTipo,
  rotuloAtivo,
  useAtivos,
  useInstituicoes,
  useTiposAtivo,
} from "@/lib/consultas-comuns";
import { ehZero, somar } from "@/lib/decimal";
import { formatarData, formatarMoeda, formatarNumero, formatarPreco } from "@/lib/formatacao";
import { DialogoTransacao } from "../transacao/DialogoTransacao";
import { useExcluirTransacao, type Operacao } from "./consultas";
import { SeloOperacao } from "./SeloOperacao";
import { NOMES_MOVIMENTO, NOMES_SUBTIPO } from "./rotulos";

const MOVIMENTOS_DE_SAIDA = new Set(["saque", "debito_compra"]);

function Linha({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{rotulo}</dt>
      <dd className="tabular">{children}</dd>
    </>
  );
}

/** Detalhe da operação: valores, resultado, movimentos de caixa gerados, editar e excluir. */
export function DetalheOperacao({
  operacao,
  aoFechar,
}: {
  operacao: Operacao;
  aoFechar: () => void;
}) {
  const ativo = useAtivos().data?.find((a) => a.id === operacao.ativo_id);
  const instituicao = useInstituicoes().data?.find((i) => i.id === operacao.instituicao_id);
  const tipos = useTiposAtivo().data;
  const excluir = useExcluirTransacao();
  const [editando, setEditando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const estrangeira = operacao.moeda !== "BRL";
  const op = operacao;

  return (
    <>
      <Dialog
        open={!editando}
        onOpenChange={(aberto) => {
          if (!aberto) aoFechar();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <SeloOperacao tipo={op.tipo} /> {rotuloAtivo(ativo)} · {formatarData(op.data)}
            </DialogTitle>
            <DialogDescription>
              {ativo?.nome}
              {ativo && ` · ${nomeDoTipo(tipos, ativo.tipo)}`} · {instituicao?.nome ?? "—"}
            </DialogDescription>
          </DialogHeader>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
            {op.quantidade !== null && (
              <>
                <Linha rotulo="Quantidade">{formatarNumero(op.quantidade)}</Linha>
                <Linha rotulo="Preço unitário">{formatarPreco(op.preco_unitario, op.moeda)}</Linha>
              </>
            )}
            {!ehZero(op.taxas) && (
              <Linha rotulo="Taxas">
                {formatarMoeda(op.taxas, op.moeda)}
                {estrangeira && ` (${formatarMoeda(op.taxas_brl)})`}
              </Linha>
            )}
            {op.tipo === "provento" && (
              <>
                <Linha rotulo="Tipo do provento">
                  {op.subtipo_provento ? NOMES_SUBTIPO[op.subtipo_provento] : "—"}
                </Linha>
                <Linha rotulo="Valor bruto">
                  {formatarMoeda(somar([op.valor ?? "0", op.imposto_retido]), op.moeda)}
                </Linha>
                <Linha rotulo="Imposto retido">{formatarMoeda(op.imposto_retido, op.moeda)}</Linha>
              </>
            )}
            {estrangeira && (
              <Linha rotulo="Câmbio">{formatarNumero(op.cambio, { maximo: 6 })}</Linha>
            )}
            <Linha rotulo={op.tipo === "provento" ? "Valor líquido" : "Valor total"}>
              {formatarMoeda(op.valor_total, op.moeda)}
              {estrangeira && ` (${formatarMoeda(op.valor_total_brl)})`}
            </Linha>
            {op.resultado_brl !== null && (
              <Linha rotulo="Resultado (lucro realizado)">
                <ValorFinanceiro valor={op.resultado_brl} />
                {estrangeira && (
                  <>
                    {" "}
                    (<ValorFinanceiro valor={op.resultado} moeda={op.moeda} seta={false} />)
                  </>
                )}
              </Linha>
            )}
            <Linha rotulo="Situação do ativo">
              {op.situacao === "aberta" ? "Ainda na carteira" : "Posição encerrada"}
            </Linha>
            {op.observacao && <Linha rotulo="Observação">{op.observacao}</Linha>}
          </dl>
          <section>
            <h3 className="mb-1 text-sm font-semibold">Movimentos de caixa gerados</h3>
            {op.movimentos.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhum (operação sem valor em caixa).</p>
            ) : (
              <ul className="grid gap-1 text-sm">
                {op.movimentos.map((m) => (
                  <li key={m.id} className="flex justify-between gap-2">
                    <span>{NOMES_MOVIMENTO[m.tipo] ?? m.tipo}</span>
                    <span className="tabular">
                      {MOVIMENTOS_DE_SAIDA.has(m.tipo) ? "−" : "+"}
                      {formatarMoeda(m.valor, op.moeda)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button
              variant="outline"
              onClick={() => {
                setEditando(true);
              }}
            >
              <Pencil aria-hidden />
              Editar
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                excluir.reset();
                setExcluindo(true);
              }}
            >
              <Trash2 aria-hidden />
              Excluir
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {editando && (
        <DialogoTransacao
          aberto={editando}
          transacao={op}
          aoMudar={(aberto) => {
            if (!aberto) aoFechar();
          }}
        />
      )}
      <DialogoConfirmacao
        aberto={excluindo}
        aoMudar={setExcluindo}
        titulo="Excluir esta operação?"
        descricao="Os movimentos de caixa gerados saem junto e a posição é recalculada. A exclusão é recusada se deixar algo inválido (ex.: uma venda posterior sem compra)."
        ocupado={excluir.isPending}
        erro={excluir.error}
        aoConfirmar={() => {
          excluir.mutate(op.id, {
            onSuccess: () => {
              setExcluindo(false);
              aoFechar();
            },
          });
        }}
      />
    </>
  );
}
