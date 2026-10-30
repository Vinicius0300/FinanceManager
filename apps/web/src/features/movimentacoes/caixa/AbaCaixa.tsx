import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { components } from "@/api/schema";
import { Secao } from "@/components/CabecalhoPagina";
import { Campo } from "@/components/Campo";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { Carregando, EstadoErro, EstadoVazio, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ValorFinanceiro } from "@/components/ValorFinanceiro";
import { exigir } from "@/lib/api";
import { useClienteApi } from "@/lib/cliente-api";
import { useGravacao, useInstituicoes, type Instituicao } from "@/lib/consultas-comuns";
import { hojeIso } from "@/lib/datas";
import {
  aplicarErrosDaApi,
  CASAS,
  dataObrigatoria,
  decimalObrigatorio,
  paraCampo,
  textoObrigatorio,
  textoOpcional,
} from "@/lib/formularios";
import { formatarData, formatarMoeda, plural } from "@/lib/formatacao";
import { cn } from "@/lib/utils";
import { NOMES_MOVIMENTO } from "../historico/rotulos";

type Conta = components["schemas"]["ContaSaida"];
type Movimento = components["schemas"]["MovimentoSaida"];

const NOMES_TIPO_INSTITUICAO = { corretora: "Corretora", banco: "Banco", outro: "Outro" } as const;
const MOVIMENTOS_EDITAVEIS = new Set(["deposito", "saque", "ajuste_saldo"]);
const MOVIMENTOS_DE_SAIDA = new Set(["saque", "debito_compra"]);
const ITENS_EXTRATO = 50;

function useContas() {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["contas"],
    queryFn: async ({ signal }) => exigir(await cliente.GET("/api/contas", { signal })),
  });
}

function useExtrato(instituicaoId: number, moeda: string, pagina: number) {
  const { cliente } = useClienteApi();
  return useQuery({
    queryKey: ["contas", "extrato", instituicaoId, moeda, pagina],
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) =>
      exigir(
        await cliente.GET("/api/instituicoes/{instituicao_id}/extrato", {
          params: {
            path: { instituicao_id: instituicaoId },
            query: { moeda, limite: ITENS_EXTRATO, deslocamento: (pagina - 1) * ITENS_EXTRATO },
          },
          signal,
        }),
      ),
  });
}

/** Instituições, saldo por instituição e moeda, extrato e depósitos/saques manuais. */
export function AbaCaixa({ agora }: { agora: Date }) {
  const instituicoes = useInstituicoes();
  const contas = useContas();
  const [selecionada, setSelecionada] = useState<{ id: number; moeda: string } | null>(null);
  const [editando, setEditando] = useState<Instituicao | "nova" | null>(null);
  const [excluindo, setExcluindo] = useState<Instituicao | null>(null);
  const { cliente } = useClienteApi();
  const excluir = useGravacao(async (id: number) => {
    exigir(
      await cliente.DELETE("/api/instituicoes/{instituicao_id}", {
        params: { path: { instituicao_id: id } },
      }),
    );
  });

  const contasDe = (id: number): Conta[] =>
    (contas.data ?? []).filter((c) => c.instituicao_id === id);
  const atual =
    selecionada ?? (instituicoes.data?.[0] ? { id: instituicoes.data[0].id, moeda: "BRL" } : null);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <Secao
        titulo="Instituições"
        acoes={
          <Button
            size="sm"
            onClick={() => {
              setEditando("nova");
            }}
          >
            <Plus aria-hidden />
            Nova instituição
          </Button>
        }
      >
        {instituicoes.isPending || contas.isPending ? (
          <Carregando />
        ) : instituicoes.isError ? (
          <EstadoErro erro={instituicoes.error} />
        ) : contas.isError ? (
          <EstadoErro erro={contas.error} />
        ) : instituicoes.data.length === 0 ? (
          <EstadoVazio
            titulo="Nenhuma instituição cadastrada"
            descricao="Cadastre a corretora ou o banco onde o dinheiro está e registre um depósito."
          />
        ) : (
          <ul className="grid gap-2">
            {instituicoes.data.map((inst) => {
              const daInstituicao = contasDe(inst.id);
              const moedas =
                daInstituicao.length > 0 ? daInstituicao : [{ moeda: "BRL", saldo: "0" }];
              return (
                <li key={inst.id} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold">{inst.nome}</p>
                      <p className="text-xs text-muted-foreground">
                        {NOMES_TIPO_INSTITUICAO[inst.tipo]}
                      </p>
                    </div>
                    <div className="flex">
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Editar ${inst.nome}`}
                        onClick={() => {
                          setEditando(inst);
                        }}
                      >
                        <Pencil aria-hidden />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Excluir ${inst.nome}`}
                        onClick={() => {
                          excluir.reset();
                          setExcluindo(inst);
                        }}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {moedas.map((c) => {
                      const ativa = atual?.id === inst.id && atual.moeda === c.moeda;
                      return (
                        <button
                          key={c.moeda}
                          type="button"
                          aria-pressed={ativa}
                          onClick={() => {
                            setSelecionada({ id: inst.id, moeda: c.moeda });
                          }}
                          className={cn(
                            "rounded-md border px-3 py-1.5 text-left text-sm hover:bg-accent",
                            ativa && "border-primary bg-accent text-accent-foreground",
                          )}
                        >
                          <span className="block text-xs text-muted-foreground">
                            Saldo em {c.moeda}
                          </span>
                          <span className="tabular font-semibold">
                            {formatarMoeda(c.saldo, c.moeda)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Secao>
      {atual && instituicoes.data?.some((i) => i.id === atual.id) && (
        <Extrato
          key={`${atual.id}-${atual.moeda}`}
          instituicao={instituicoes.data.find((i) => i.id === atual.id) as Instituicao}
          moeda={atual.moeda}
          hoje={hojeIso(agora)}
        />
      )}
      {editando && (
        <DialogoInstituicao
          instituicao={editando === "nova" ? undefined : editando}
          aoFechar={() => {
            setEditando(null);
          }}
        />
      )}
      <DialogoConfirmacao
        aberto={excluindo !== null}
        aoMudar={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo={`Excluir ${excluindo?.nome ?? "instituição"}?`}
        descricao="Só é possível excluir uma instituição sem transações e sem movimentos de caixa."
        ocupado={excluir.isPending}
        erro={excluir.error}
        aoConfirmar={() => {
          if (!excluindo) return;
          excluir.mutate(excluindo.id, {
            onSuccess: () => {
              setExcluindo(null);
              setSelecionada(null);
            },
          });
        }}
      />
    </div>
  );
}

function Extrato({
  instituicao,
  moeda,
  hoje,
}: {
  instituicao: Instituicao;
  moeda: string;
  hoje: string;
}) {
  const [pagina, setPagina] = useState(1);
  const extrato = useExtrato(instituicao.id, moeda, pagina);
  const [movimento, setMovimento] = useState<
    { tipo: "deposito" | "saque" } | { editar: Movimento } | null
  >(null);
  const [excluindo, setExcluindo] = useState<Movimento | null>(null);
  const { cliente } = useClienteApi();
  const excluir = useGravacao(async (id: number) => {
    exigir(
      await cliente.DELETE("/api/movimentos/{movimento_id}", {
        params: { path: { movimento_id: id } },
      }),
    );
  });
  const paginas = Math.max(1, Math.ceil((extrato.data?.total ?? 0) / ITENS_EXTRATO));

  return (
    <Secao
      titulo={`Extrato · ${instituicao.nome} (${moeda})`}
      acoes={
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setMovimento({ tipo: "deposito" });
            }}
          >
            Depósito
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setMovimento({ tipo: "saque" });
            }}
          >
            Saque
          </Button>
        </div>
      }
    >
      {extrato.isPending ? (
        <Carregando />
      ) : extrato.isError ? (
        <EstadoErro
          erro={extrato.error}
          aoTentarNovamente={() => {
            void extrato.refetch();
          }}
        />
      ) : (
        <>
          <p className="mb-2 text-sm">
            Saldo atual:{" "}
            <span className="tabular font-semibold">
              {formatarMoeda(extrato.data.saldo_final, moeda)}
            </span>
          </p>
          {extrato.data.itens.length === 0 ? (
            <EstadoVazio titulo="Nenhum movimento nesta conta" />
          ) : (
            <Table aria-label="Extrato">
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Movimento</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {extrato.data.itens.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="tabular">{formatarData(m.data)}</TableCell>
                    <TableCell>
                      {NOMES_MOVIMENTO[m.tipo] ?? m.tipo}
                      {m.descricao && (
                        <span className="block text-xs text-muted-foreground">{m.descricao}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <ValorFinanceiro
                        valor={MOVIMENTOS_DE_SAIDA.has(m.tipo) ? `-${m.valor}` : m.valor}
                        moeda={moeda}
                        seta={false}
                      />
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      {MOVIMENTOS_EDITAVEIS.has(m.tipo) && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`Alterar valor de ${formatarData(m.data)}`}
                            onClick={() => {
                              setMovimento({ editar: m });
                            }}
                          >
                            <Pencil aria-hidden />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`Excluir movimento de ${formatarData(m.data)}`}
                            onClick={() => {
                              excluir.reset();
                              setExcluindo(m);
                            }}
                          >
                            <Trash2 aria-hidden />
                          </Button>
                        </>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {paginas > 1 && (
            <nav
              aria-label="Paginação do extrato"
              className="mt-2 flex items-center justify-end gap-2 text-xs"
            >
              <Button
                size="sm"
                variant="outline"
                disabled={pagina <= 1}
                onClick={() => {
                  setPagina(pagina - 1);
                }}
              >
                Anterior
              </Button>
              Página {pagina} de {paginas} · {plural(extrato.data.total, "movimento", "movimentos")}
              <Button
                size="sm"
                variant="outline"
                disabled={pagina >= paginas}
                onClick={() => {
                  setPagina(pagina + 1);
                }}
              >
                Próxima
              </Button>
            </nav>
          )}
        </>
      )}
      {movimento && (
        <DialogoMovimento
          instituicao={instituicao}
          moeda={moeda}
          hoje={hoje}
          {...("editar" in movimento ? { movimento: movimento.editar } : { tipo: movimento.tipo })}
          aoFechar={() => {
            setMovimento(null);
          }}
        />
      )}
      <DialogoConfirmacao
        aberto={excluindo !== null}
        aoMudar={(aberto) => {
          if (!aberto) setExcluindo(null);
        }}
        titulo="Excluir este movimento?"
        descricao="O saldo é recalculado. A exclusão é recusada se o saldo ficar negativo em algum dia."
        ocupado={excluir.isPending}
        erro={excluir.error}
        aoConfirmar={() => {
          if (!excluindo) return;
          excluir.mutate(excluindo.id, {
            onSuccess: () => {
              setExcluindo(null);
            },
          });
        }}
      />
    </Secao>
  );
}

const esquemaInstituicao = z.object({
  nome: textoObrigatorio(100),
  tipo: z.enum(["corretora", "banco", "outro"]),
});

function DialogoInstituicao({
  instituicao,
  aoFechar,
}: {
  instituicao?: Instituicao;
  aoFechar: () => void;
}) {
  const { cliente } = useClienteApi();
  const salvar = useGravacao(async (corpo: z.output<typeof esquemaInstituicao>) =>
    instituicao
      ? exigir(
          await cliente.PUT("/api/instituicoes/{instituicao_id}", {
            params: { path: { instituicao_id: instituicao.id } },
            body: corpo,
          }),
        )
      : exigir(await cliente.POST("/api/instituicoes", { body: corpo })),
  );
  const form = useForm<
    z.input<typeof esquemaInstituicao>,
    unknown,
    z.output<typeof esquemaInstituicao>
  >({
    resolver: zodResolver(esquemaInstituicao),
    defaultValues: { nome: instituicao?.nome ?? "", tipo: instituicao?.tipo ?? "corretora" },
  });
  const enviar = form.handleSubmit(async (dados) => {
    try {
      await salvar.mutateAsync(dados);
      aoFechar();
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, ["nome", "tipo"]);
    }
  });
  return (
    <Dialog
      open
      onOpenChange={(aberto) => {
        if (!aberto) aoFechar();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{instituicao ? "Editar instituição" : "Nova instituição"}</DialogTitle>
          <DialogDescription>
            Onde o dinheiro está alocado. Cada instituição tem uma conta corrente por moeda.
          </DialogDescription>
        </DialogHeader>
        <form
          noValidate
          className="grid gap-4"
          onSubmit={(e) => {
            void enviar(e);
          }}
        >
          <Campo rotulo="Nome" obrigatorio erro={form.formState.errors.nome?.message}>
            <Input maxLength={100} {...form.register("nome")} />
          </Campo>
          <Campo rotulo="Tipo" erro={form.formState.errors.tipo?.message}>
            <Select {...form.register("tipo")}>
              {Object.entries(NOMES_TIPO_INSTITUICAO).map(([valor, rotulo]) => (
                <option key={valor} value={valor}>
                  {rotulo}
                </option>
              ))}
            </Select>
          </Campo>
          <MensagemErro erro={salvar.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={aoFechar} disabled={salvar.isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={salvar.isPending}>
              {salvar.isPending && <Loader2 aria-hidden className="animate-spin" />}
              Salvar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function criarEsquemaMovimento(hoje: string) {
  return z.object({
    data: dataObrigatoria.refine((d) => d <= hoje, "A data não pode ser futura."),
    valor: decimalObrigatorio({ casas: CASAS.moeda, sinal: "positivo" }),
    descricao: textoOpcional(200),
  });
}

/** Depósito/saque novo, ou alteração do valor de um movimento existente. */
function DialogoMovimento({
  instituicao,
  moeda,
  hoje,
  tipo,
  movimento,
  aoFechar,
}: {
  instituicao: Instituicao;
  moeda: string;
  hoje: string;
  tipo?: "deposito" | "saque";
  movimento?: Movimento;
  aoFechar: () => void;
}) {
  const { cliente } = useClienteApi();
  const esquema = criarEsquemaMovimento(movimento ? "9999-12-31" : hoje);
  const salvar = useGravacao(async (dados: z.output<typeof esquema>) =>
    movimento
      ? exigir(
          await cliente.PATCH("/api/movimentos/{movimento_id}", {
            params: { path: { movimento_id: movimento.id } },
            body: { valor: dados.valor },
          }),
        )
      : exigir(
          await cliente.POST("/api/movimentos", {
            body: {
              instituicao_id: instituicao.id,
              moeda,
              tipo: tipo ?? "deposito",
              data: dados.data,
              valor: dados.valor,
              descricao: dados.descricao,
            },
          }),
        ),
  );
  const form = useForm<z.input<typeof esquema>, unknown, z.output<typeof esquema>>({
    resolver: zodResolver(esquema),
    defaultValues: {
      data: movimento?.data ?? hoje,
      valor: paraCampo(movimento?.valor),
      descricao: movimento?.descricao ?? "",
    },
  });
  const erros = form.formState.errors;
  const enviar = form.handleSubmit(async (dados) => {
    try {
      await salvar.mutateAsync(dados);
      aoFechar();
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, ["data", "valor", "descricao"]);
    }
  });
  const titulo = movimento
    ? `Alterar valor: ${NOMES_MOVIMENTO[movimento.tipo] ?? movimento.tipo}`
    : tipo === "saque"
      ? "Novo saque"
      : "Novo depósito";
  return (
    <Dialog
      open
      onOpenChange={(aberto) => {
        if (!aberto) aoFechar();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>
            {instituicao.nome} · conta em {moeda}
          </DialogDescription>
        </DialogHeader>
        <form
          noValidate
          className="grid gap-4"
          onSubmit={(e) => {
            void enviar(e);
          }}
        >
          <Campo
            rotulo="Data"
            erro={erros.data?.message}
            ajuda={movimento ? "Só o valor pode ser alterado." : undefined}
          >
            <Input
              type="date"
              max={hoje}
              disabled={movimento !== undefined}
              {...form.register("data")}
            />
          </Campo>
          <Campo rotulo={`Valor (${moeda})`} obrigatorio erro={erros.valor?.message}>
            <Input inputMode="decimal" placeholder="0,00" {...form.register("valor")} />
          </Campo>
          {!movimento && (
            <Campo rotulo="Descrição" erro={erros.descricao?.message}>
              <Input maxLength={200} {...form.register("descricao")} />
            </Campo>
          )}
          <MensagemErro erro={salvar.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={aoFechar} disabled={salvar.isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={salvar.isPending}>
              {salvar.isPending && <Loader2 aria-hidden className="animate-spin" />}
              Salvar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
