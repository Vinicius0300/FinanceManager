import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import type { z } from "zod";
import { Campo } from "@/components/Campo";
import { Carregando, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import {
  nomeDoTipo,
  rotuloAtivo,
  useAtivos,
  useInstituicoes,
  useTiposAtivo,
} from "@/lib/consultas-comuns";
import { hojeIso } from "@/lib/datas";
import { aplicarErrosDaApi } from "@/lib/formularios";
import { NOMES_OPERACAO, OPERACOES } from "../historico/filtros";
import {
  criarEsquemaTransacao,
  SUBTIPOS_PROVENTO,
  usaQuantidade,
  valoresIniciais,
  type RegrasDoAtivo,
  type TransacaoEntrada,
  type TransacaoSaida,
  type ValoresTransacao,
} from "./esquema";
import { useSalvarTransacao } from "./consultas";
import { DialogoSaldoInsuficiente } from "./DialogoSaldoInsuficiente";
import { lerSaldoInsuficiente, type SaldoInsuficiente } from "./saldo";

const CAMPOS = [
  "tipo",
  "ativo_id",
  "instituicao_id",
  "data",
  "quantidade",
  "preco_unitario",
  "valor",
  "taxas",
  "cambio",
  "subtipo_provento",
  "imposto_retido",
  "observacao",
] as const;

/**
 * Cadastro e edição de transações de investimento (compra, venda, aporte, resgate,
 * provento). Na edição o ativo fica bloqueado (a API não permite trocá-lo).
 * Se a API responder 409 de saldo insuficiente, abre o diálogo de confirmação.
 */
export function DialogoTransacao({
  aberto,
  aoMudar,
  transacao,
  agora = new Date(),
}: {
  aberto: boolean;
  aoMudar: (aberto: boolean) => void;
  transacao?: TransacaoSaida;
  agora?: Date;
}) {
  const ativos = useAtivos();
  const instituicoes = useInstituicoes();
  const tipos = useTiposAtivo();
  const salvar = useSalvarTransacao();
  const [pendente, setPendente] = useState<{
    corpo: TransacaoEntrada;
    saldo: SaldoInsuficiente;
  } | null>(null);
  const edicao = transacao !== undefined;

  const regras = useMemo(
    () =>
      (ativoId: number): RegrasDoAtivo | undefined => {
        const ativo = ativos.data?.find((a) => a.id === ativoId);
        const tipo = tipos.data?.find((t) => t.slug === ativo?.tipo);
        if (!ativo || !tipo) return undefined;
        return {
          moeda: ativo.moeda,
          tiposAceitos: tipo.tipos_transacao,
          aceitaTaxas: tipo.aceita_taxas,
        };
      },
    [ativos.data, tipos.data],
  );
  const esquema = useMemo(() => criarEsquemaTransacao(regras), [regras]);
  const form = useForm<ValoresTransacao, unknown, z.output<typeof esquema>>({
    resolver: zodResolver(esquema),
    defaultValues: valoresIniciais(hojeIso(agora), transacao),
  });
  const erros = form.formState.errors;
  const tipo = useWatch({ control: form.control, name: "tipo" });
  const ativoId = useWatch({ control: form.control, name: "ativo_id" });
  const regrasAtivo = ativoId ? regras(Number(ativoId)) : undefined;
  const moeda = regrasAtivo?.moeda ?? "BRL";

  const fechar = () => {
    salvar.reset();
    setPendente(null);
    aoMudar(false);
  };

  const enviar = async (corpo: TransacaoEntrada) => {
    try {
      await salvar.mutateAsync({ id: transacao?.id, corpo });
      fechar();
    } catch (falha) {
      const saldo = lerSaldoInsuficiente(falha);
      if (saldo) {
        salvar.reset();
        setPendente({ corpo, saldo });
        return;
      }
      aplicarErrosDaApi(falha, form.setError, CAMPOS);
    }
  };

  const aoEnviar = form.handleSubmit(enviar);

  return (
    <>
      <Dialog
        open={aberto}
        onOpenChange={(abrir) => {
          if (!abrir) fechar();
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{edicao ? "Editar operação" : "Nova movimentação"}</DialogTitle>
            <DialogDescription>
              Compras e aportes debitam a conta da instituição; vendas, resgates e proventos
              creditam.
            </DialogDescription>
          </DialogHeader>
          {ativos.isPending || instituicoes.isPending || tipos.isPending ? (
            <Carregando />
          ) : (
            <form
              noValidate
              onSubmit={(e) => {
                void aoEnviar(e);
              }}
              className="grid gap-4"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Campo rotulo="Operação" obrigatorio erro={erros.tipo?.message}>
                  <Select {...form.register("tipo")}>
                    {OPERACOES.map((op) => (
                      <option key={op} value={op}>
                        {NOMES_OPERACAO[op]}
                      </option>
                    ))}
                  </Select>
                </Campo>
                <Campo rotulo="Data" obrigatorio erro={erros.data?.message}>
                  <Input type="date" {...form.register("data")} />
                </Campo>
                <Campo
                  rotulo="Ativo"
                  obrigatorio
                  erro={erros.ativo_id?.message}
                  ajuda={edicao ? "O ativo não pode ser trocado na edição." : undefined}
                >
                  <Select {...form.register("ativo_id")} disabled={edicao}>
                    <option value="">Escolha…</option>
                    {ativos.data?.map((a) => (
                      <option key={a.id} value={a.id}>
                        {rotuloAtivo(a)} · {nomeDoTipo(tipos.data, a.tipo)} ({a.moeda})
                      </option>
                    ))}
                  </Select>
                </Campo>
                <Campo rotulo="Instituição" obrigatorio erro={erros.instituicao_id?.message}>
                  <Select {...form.register("instituicao_id")}>
                    <option value="">Escolha…</option>
                    {instituicoes.data?.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.nome}
                      </option>
                    ))}
                  </Select>
                </Campo>
                {usaQuantidade(tipo) ? (
                  <>
                    <Campo rotulo="Quantidade" obrigatorio erro={erros.quantidade?.message}>
                      <Input inputMode="decimal" {...form.register("quantidade")} />
                    </Campo>
                    <Campo
                      rotulo={`Preço unitário (${moeda})`}
                      obrigatorio
                      erro={erros.preco_unitario?.message}
                    >
                      <Input inputMode="decimal" {...form.register("preco_unitario")} />
                    </Campo>
                    {regrasAtivo?.aceitaTaxas !== false && (
                      <Campo rotulo={`Taxas (${moeda})`} erro={erros.taxas?.message}>
                        <Input inputMode="decimal" placeholder="0,00" {...form.register("taxas")} />
                      </Campo>
                    )}
                  </>
                ) : (
                  <Campo
                    rotulo={
                      tipo === "provento" ? `Valor líquido recebido (${moeda})` : `Valor (${moeda})`
                    }
                    obrigatorio
                    erro={erros.valor?.message}
                  >
                    <Input inputMode="decimal" {...form.register("valor")} />
                  </Campo>
                )}
                {tipo === "provento" && (
                  <>
                    <Campo
                      rotulo="Tipo do provento"
                      obrigatorio
                      erro={erros.subtipo_provento?.message}
                    >
                      <Select {...form.register("subtipo_provento")}>
                        {SUBTIPOS_PROVENTO.map((s) => (
                          <option key={s.valor} value={s.valor}>
                            {s.rotulo}
                          </option>
                        ))}
                      </Select>
                    </Campo>
                    <Campo
                      rotulo={`Imposto retido (${moeda})`}
                      erro={erros.imposto_retido?.message}
                      ajuda="IR descontado na fonte (fica registrado à parte)."
                    >
                      <Input
                        inputMode="decimal"
                        placeholder="0,00"
                        {...form.register("imposto_retido")}
                      />
                    </Campo>
                  </>
                )}
                {moeda !== "BRL" && (
                  <Campo
                    rotulo={`Câmbio pago (R$ por ${moeda})`}
                    erro={erros.cambio?.message}
                    ajuda="Opcional. Se vazio, usa a PTAX da data."
                  >
                    <Input
                      inputMode="decimal"
                      placeholder="ex.: 5,4321"
                      {...form.register("cambio")}
                    />
                  </Campo>
                )}
                <Campo
                  rotulo="Observação"
                  erro={erros.observacao?.message}
                  className="sm:col-span-2"
                >
                  <Textarea rows={2} maxLength={500} {...form.register("observacao")} />
                </Campo>
              </div>
              <MensagemErro erro={salvar.error} />
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={fechar}
                  disabled={salvar.isPending}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={salvar.isPending}>
                  {salvar.isPending && <Loader2 aria-hidden className="animate-spin" />}
                  {edicao ? "Salvar alterações" : "Registrar"}
                </Button>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
      <DialogoSaldoInsuficiente
        saldo={pendente?.saldo ?? null}
        ocupado={salvar.isPending}
        erro={salvar.error}
        aoCancelar={() => {
          setPendente(null);
          salvar.reset();
        }}
        aoContinuar={() => {
          if (!pendente) return;
          void enviar({ ...pendente.corpo, aceitar_ajuste: true });
        }}
      />
    </>
  );
}
