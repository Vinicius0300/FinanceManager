import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Controller, useForm, useWatch, type UseFormReturn } from "react-hook-form";
import type { z } from "zod";
import { Campo } from "@/components/Campo";
import { Carregando, EstadoErro, MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { AJUDA_SIMBOLO_EXTERNO } from "@/features/carteira/esquemaAtivo";
import {
  nomeDoTipo,
  rotuloAtivo,
  useAtivos,
  useInstituicoes,
  useTiposAtivo,
  type Ativo,
  type Instituicao,
  type TipoAtivo,
} from "@/lib/consultas-comuns";
import { hojeIso } from "@/lib/datas";
import { comparar, normalizarDecimal } from "@/lib/decimal";
import { formatarMoeda, formatarNumero } from "@/lib/formatacao";
import { aplicarErrosDaApi } from "@/lib/formularios";
import { NOMES_OPERACAO, OPERACOES } from "../historico/filtros";
import { AtivoEscolhido, BuscaAtivo, type Escolha } from "./BuscaAtivo";
import {
  useEditarTransacao,
  usePosicoesNaData,
  useRegistrarMovimentacao,
  type Posicao,
} from "./consultas";
import { DialogoAtivoSemelhante } from "./DialogoAtivoSemelhante";
import { DialogoSaldoInsuficiente } from "./DialogoSaldoInsuficiente";
import {
  CAMPOS_COM_A_DATA_DA_OPERACAO,
  criaAtivo,
  criarEsquemaTransacao,
  novoAtivoVazio,
  operacaoAceita,
  paraTransacaoEntrada,
  SUBTIPOS_PROVENTO,
  usaQuantidade,
  valoresIniciais,
  type MovimentacaoEntrada,
  type TransacaoSaida,
  type ValoresTransacao,
} from "./esquema";
import {
  lerAtivoSemelhante,
  lerSaldoInsuficiente,
  type AtivoSemelhante,
  type SaldoInsuficiente,
} from "./saldo";

const CAMPOS_TRANSACAO = [
  "tipo_ativo",
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

const VALOR_NOVO = "novo";

type Formulario = UseFormReturn<
  ValoresTransacao,
  unknown,
  z.output<ReturnType<typeof criarEsquemaTransacao>>
>;

/**
 * Formulário único de movimentação (Parte 4.1): tipo de ativo → operação → ativo → dados.
 * Compra e aporte procuram o ativo (ou o cadastram na hora, junto com a transação);
 * venda e resgate listam só as posições da instituição na data, com o disponível.
 * Na edição o ativo fica bloqueado (a API não permite trocá-lo).
 * Respostas 409: saldo insuficiente e título semelhante abrem a confirmação.
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
  const edicao = transacao !== undefined;
  const consultas = [ativos, instituicoes, tipos];
  const falha = consultas.find((c) => c.isError);

  return (
    <Dialog
      open={aberto}
      onOpenChange={(abrir) => {
        if (!abrir) aoMudar(false);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{edicao ? "Editar operação" : "Nova movimentação"}</DialogTitle>
          <DialogDescription>
            Compras e aportes debitam a conta da instituição; vendas, resgates e proventos creditam.
          </DialogDescription>
        </DialogHeader>
        {falha ? (
          <EstadoErro
            erro={falha.error}
            aoTentarNovamente={() => {
              for (const consulta of consultas) void consulta.refetch();
            }}
          />
        ) : ativos.data && instituicoes.data && tipos.data ? (
          <FormularioMovimentacao
            ativos={ativos.data}
            instituicoes={instituicoes.data}
            tipos={tipos.data}
            transacao={transacao}
            hoje={hojeIso(agora)}
            aoFechar={() => {
              aoMudar(false);
            }}
          />
        ) : (
          <Carregando />
        )}
      </DialogContent>
    </Dialog>
  );
}

function FormularioMovimentacao({
  ativos,
  instituicoes,
  tipos,
  transacao,
  hoje,
  aoFechar,
}: {
  ativos: Ativo[];
  instituicoes: Instituicao[];
  tipos: TipoAtivo[];
  transacao: TransacaoSaida | undefined;
  hoje: string;
  aoFechar: () => void;
}) {
  const edicao = transacao !== undefined;
  const ativoEditado = ativos.find((a) => a.id === transacao?.ativo_id);
  const tipoPorSlug = useMemo(() => new Map(tipos.map((t) => [t.slug, t])), [tipos]);
  const esquema = useMemo(
    () =>
      criarEsquemaTransacao({
        tipo: (slug) => tipoPorSlug.get(slug),
        moedaDoAtivo: (id) => ativos.find((a) => a.id === id)?.moeda,
      }),
    [tipoPorSlug, ativos],
  );
  const form: Formulario = useForm({
    resolver: zodResolver(esquema),
    defaultValues: valoresIniciais(
      hoje,
      transacao,
      ativoEditado ? tipoPorSlug.get(ativoEditado.tipo) : undefined,
    ),
  });
  const registrar = useRegistrarMovimentacao();
  const editar = useEditarTransacao();
  const mutacao = edicao ? editar : registrar;
  const [escolha, setEscolha] = useState<Escolha | null>(null);
  const [pendente, setPendente] = useState<{
    corpo: MovimentacaoEntrada;
    saldo?: SaldoInsuficiente;
    semelhante?: AtivoSemelhante;
  } | null>(null);

  const erros = form.formState.errors;
  const slug = useWatch({ control: form.control, name: "tipo_ativo" });
  const operacao = useWatch({ control: form.control, name: "tipo" });
  const modo = useWatch({ control: form.control, name: "modo_ativo" });
  const ativoId = useWatch({ control: form.control, name: "ativo_id" });
  const moedaNova = useWatch({ control: form.control, name: "novo_ativo.moeda" });
  const instituicaoId = useWatch({ control: form.control, name: "instituicao_id" });
  const data = useWatch({ control: form.control, name: "data" });
  const tipoAtivo = tipoPorSlug.get(slug);
  const ativoAtual = ativos.find((a) => String(a.id) === ativoId);
  const moeda =
    modo === "novo"
      ? moedaNova || (tipoAtivo?.moeda_padrao ?? "BRL")
      : (ativoAtual?.moeda ?? "BRL");
  const precisaPosicao = !edicao && !criaAtivo(operacao);
  const posicoes = usePosicoesNaData(
    precisaPosicao && instituicaoId !== "" ? Number(instituicaoId) : null,
    data,
  );

  const limparAtivo = (tipo: TipoAtivo | undefined) => {
    form.setValue("modo_ativo", "");
    form.setValue("ativo_id", "");
    form.setValue("novo_ativo", novoAtivoVazio(tipo));
    form.clearErrors(["ativo_id", "novo_ativo"]);
    setEscolha(null);
  };

  /** Aplica um resultado da busca para o tipo informado (cadastrado ou novo). */
  const aplicarEscolha = (nova: Escolha, tipo: TipoAtivo) => {
    form.clearErrors(["ativo_id", "novo_ativo"]);
    setEscolha(nova);
    if (nova.origem === "resultado" && nova.item.ativo_id !== null) {
      const cadastrado = tipoPorSlug.get(nova.item.tipo ?? "");
      if (cadastrado && cadastrado.slug !== tipo.slug) {
        // O ativo já existe com outro tipo: a movimentação é nele, então o tipo segue o dele.
        form.setValue("tipo_ativo", cadastrado.slug);
        form.setValue("tipo", operacaoAceita(cadastrado, form.getValues("tipo")));
      }
      form.setValue("modo_ativo", "existente");
      form.setValue("ativo_id", String(nova.item.ativo_id));
      return;
    }
    const vazio = novoAtivoVazio(tipo);
    const item = nova.origem === "resultado" ? nova.item : null;
    const sugeridos = Object.fromEntries(
      Object.entries(item?.campos_sugeridos ?? {}).filter(([nome]) => nome in vazio.metadados),
    );
    form.setValue("modo_ativo", "novo");
    form.setValue("ativo_id", "");
    form.setValue("novo_ativo", {
      ...vazio,
      simbolo: item?.simbolo ?? (nova.origem === "manual" ? nova.simbolo : ""),
      nome: item?.nome ?? "",
      simbolo_externo: item?.simbolo_externo ?? "",
      metadados: { ...vazio.metadados, ...sugeridos },
    });
  };

  const trocarTipo = (novoSlug: string, manter?: Escolha) => {
    const tipo = tipoPorSlug.get(novoSlug);
    form.setValue("tipo_ativo", novoSlug);
    form.setValue("tipo", operacaoAceita(tipo, form.getValues("tipo")));
    limparAtivo(tipo);
    if (manter && tipo) aplicarEscolha(manter, tipo);
  };

  const fecharTudo = () => {
    registrar.reset();
    editar.reset();
    setPendente(null);
    aoFechar();
  };

  const enviar = async (corpo: MovimentacaoEntrada) => {
    try {
      if (transacao) {
        await editar.mutateAsync({
          id: transacao.id,
          corpo: paraTransacaoEntrada(corpo, transacao.ativo_id),
        });
      } else {
        await registrar.mutateAsync(corpo);
      }
      fecharTudo();
    } catch (falha) {
      const saldo = lerSaldoInsuficiente(falha);
      const semelhante = lerAtivoSemelhante(falha);
      if (saldo || semelhante) {
        mutacao.reset();
        setPendente({ corpo, ...(saldo ? { saldo } : {}), ...(semelhante ? { semelhante } : {}) });
        return;
      }
      setPendente(null);
      const metadados = tipoAtivo?.campos.map((c) => c.nome) ?? [];
      aplicarErrosDaApi(
        falha,
        form.setError,
        [
          ...CAMPOS_TRANSACAO,
          "novo_ativo.nome",
          "novo_ativo.simbolo",
          "novo_ativo.moeda",
          "novo_ativo.simbolo_externo",
          ...metadados.map((n) => `novo_ativo.metadados.${n}`),
        ],
        {
          nome: "novo_ativo.nome",
          simbolo: "novo_ativo.simbolo",
          moeda: "novo_ativo.moeda",
          simbolo_externo: "novo_ativo.simbolo_externo",
          ...Object.fromEntries(metadados.map((n) => [n, `novo_ativo.metadados.${n}`])),
        },
      );
    }
  };

  const aoEnviar = form.handleSubmit(enviar);
  const operacoesDoTipo = OPERACOES.filter((op) => tipoAtivo?.tipos_transacao.includes(op));

  return (
    <>
      <form
        noValidate
        onSubmit={(e) => {
          void aoEnviar(e);
        }}
        className="grid gap-4"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo
            rotulo="Tipo de ativo"
            obrigatorio
            erro={erros.tipo_ativo?.message}
            ajuda={edicao ? "O tipo não muda na edição." : tipoAtivo?.descricao}
          >
            <Select
              value={slug}
              disabled={edicao}
              onChange={(e) => {
                trocarTipo(e.target.value);
              }}
            >
              <option value="">Escolha…</option>
              {tipos.map((t) => (
                <option key={t.slug} value={t.slug}>
                  {t.nome}
                </option>
              ))}
            </Select>
          </Campo>
          <Campo rotulo="Operação" obrigatorio erro={erros.tipo?.message}>
            <Select
              {...form.register("tipo", {
                onChange: (e: { target: { value: string } }) => {
                  // Trocar entre "cria ativo" (compra/aporte) e "usa posição" limpa o ativo.
                  const antes = criaAtivo(operacao);
                  const depois = criaAtivo(e.target.value as typeof operacao);
                  if (!edicao && antes !== depois) limparAtivo(tipoAtivo);
                },
              })}
              disabled={!tipoAtivo}
            >
              {(tipoAtivo ? operacoesDoTipo : OPERACOES).map((op) => (
                <option key={op} value={op}>
                  {NOMES_OPERACAO[op]}
                </option>
              ))}
            </Select>
          </Campo>
          <Campo rotulo="Data" obrigatorio erro={erros.data?.message}>
            <Input type="date" {...form.register("data")} />
          </Campo>
          <Campo rotulo="Instituição" obrigatorio erro={erros.instituicao_id?.message}>
            <Select {...form.register("instituicao_id")}>
              <option value="">Escolha…</option>
              {instituicoes.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.nome}
                </option>
              ))}
            </Select>
          </Campo>
          <div className="sm:col-span-2">
            {edicao ? (
              <AtivoEscolhido
                titulo={rotuloAtivo(ativoEditado)}
                detalhe={`${ativoEditado?.nome ?? ""} · O ativo não pode ser trocado na edição.`}
                bloqueado
                aoTrocar={() => undefined}
              />
            ) : !tipoAtivo ? (
              <p className="text-sm text-muted-foreground">
                Escolha o tipo de ativo para buscar ou cadastrar o ativo.
              </p>
            ) : criaAtivo(operacao) ? (
              <EscolhaParaCompra
                form={form}
                tipo={tipoAtivo}
                tipos={tipos}
                ativos={ativos}
                escolha={escolha}
                aoEscolher={(nova) => {
                  aplicarEscolha(nova, tipoAtivo);
                }}
                aoTrocarTipo={trocarTipo}
                aoLimpar={() => {
                  limparAtivo(tipoAtivo);
                }}
              />
            ) : (
              <EscolhaDePosicao
                form={form}
                tipo={tipoAtivo}
                ativos={ativos}
                operacao={operacao}
                instituicaoEscolhida={instituicaoId !== ""}
                posicoes={posicoes}
              />
            )}
          </div>
          {modo === "novo" && tipoAtivo && !edicao && (
            <CamposNovoAtivo form={form} tipo={tipoAtivo} escolha={escolha} />
          )}
          {tipoAtivo && (
            <CamposDaOperacao
              form={form}
              tipo={tipoAtivo}
              moeda={moeda}
              posicao={
                precisaPosicao && operacao !== "provento"
                  ? posicoes.data?.find((p) => String(p.ativo_id) === ativoId)
                  : undefined
              }
            />
          )}
          <Campo rotulo="Observação" erro={erros.observacao?.message} className="sm:col-span-2">
            <Textarea rows={2} maxLength={500} {...form.register("observacao")} />
          </Campo>
        </div>
        <MensagemErro erro={mutacao.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={fecharTudo} disabled={mutacao.isPending}>
            Cancelar
          </Button>
          <Button type="submit" disabled={mutacao.isPending}>
            {mutacao.isPending && <Loader2 aria-hidden className="animate-spin" />}
            {edicao ? "Salvar alterações" : "Registrar"}
          </Button>
        </div>
      </form>
      <DialogoSaldoInsuficiente
        saldo={pendente?.saldo ?? null}
        ocupado={mutacao.isPending}
        erro={mutacao.error}
        aoCancelar={() => {
          setPendente(null);
          mutacao.reset();
        }}
        aoContinuar={() => {
          if (!pendente) return;
          void enviar({ ...pendente.corpo, aceitar_ajuste: true });
        }}
      />
      <DialogoAtivoSemelhante
        semelhante={pendente?.semelhante ?? null}
        ocupado={mutacao.isPending}
        erro={mutacao.error}
        aoCancelar={() => {
          setPendente(null);
          mutacao.reset();
        }}
        aoSomar={() => {
          if (!pendente?.semelhante) return;
          void enviar({ ...pendente.corpo, usar_ativo_id: pendente.semelhante.ativoId });
        }}
        aoSeparar={() => {
          if (!pendente) return;
          void enviar({ ...pendente.corpo, confirmar_novo: true });
        }}
      />
    </>
  );
}

/** Compra e aporte: busca por ticker (com lista oficial) ou lista dos ativos do tipo + "novo". */
function EscolhaParaCompra({
  form,
  tipo,
  tipos,
  ativos,
  escolha,
  aoEscolher,
  aoTrocarTipo,
  aoLimpar,
}: {
  form: Formulario;
  tipo: TipoAtivo;
  tipos: TipoAtivo[];
  ativos: Ativo[];
  escolha: Escolha | null;
  aoEscolher: (escolha: Escolha) => void;
  aoTrocarTipo: (slug: string, manter?: Escolha) => void;
  aoLimpar: () => void;
}) {
  const modo = useWatch({ control: form.control, name: "modo_ativo" });
  const ativoId = useWatch({ control: form.control, name: "ativo_id" });
  const erros = form.formState.errors;
  const erroAtivo = erros.ativo_id?.message;

  if (!tipo.busca_por_ticker) {
    const doTipo = ativos.filter((a) => a.tipo === tipo.slug);
    return (
      <Campo
        rotulo="Ativo"
        obrigatorio
        erro={erroAtivo}
        ajuda={
          modo === "novo"
            ? "Preencha os dados do novo ativo abaixo."
            : doTipo.length === 0
              ? `Nenhum ativo de ${tipo.nome} cadastrado: escolha "Novo".`
              : undefined
        }
      >
        <Select
          value={modo === "novo" ? VALOR_NOVO : ativoId}
          onChange={(e) => {
            const valor = e.target.value;
            form.clearErrors(["ativo_id", "novo_ativo"]);
            if (valor === VALOR_NOVO) {
              const vazio = novoAtivoVazio(tipo);
              form.setValue("modo_ativo", "novo");
              form.setValue("ativo_id", "");
              form.setValue("novo_ativo", {
                ...vazio,
                nome: tipo.slug === "poupanca" ? "Poupança" : "",
              });
            } else {
              form.setValue("modo_ativo", valor === "" ? "" : "existente");
              form.setValue("ativo_id", valor);
            }
          }}
        >
          <option value="">Escolha…</option>
          {doTipo.map((a) => (
            <option key={a.id} value={a.id}>
              {rotuloAtivo(a)}
              {a.simbolo ? ` · ${a.nome}` : ""}
            </option>
          ))}
          <option value={VALOR_NOVO}>Novo: cadastrar agora</option>
        </Select>
      </Campo>
    );
  }

  if (escolha === null || modo === "") {
    return <BuscaAtivo tipo={tipo} tipos={tipos} erro={erroAtivo} aoEscolher={aoEscolher} />;
  }

  const item = escolha.origem === "resultado" ? escolha.item : null;
  const titulo =
    modo === "existente"
      ? rotuloAtivo(ativos.find((a) => String(a.id) === ativoId))
      : (item?.simbolo ?? (escolha.origem === "manual" ? escolha.simbolo : ""));
  const detalhe = item
    ? `${item.nome}${modo === "existente" ? " · já na carteira" : " · novo, será cadastrado"}`
    : "Novo, será cadastrado";
  const tipoOficial = item && item.origem !== "carteira" ? item.tipo : undefined;

  return (
    <div className="grid gap-2">
      <AtivoEscolhido titulo={titulo} detalhe={detalhe} aoTrocar={aoLimpar} />
      {tipoOficial !== undefined && tipoOficial !== null && tipoOficial !== tipo.slug && (
        <Aviso>
          Na lista oficial, {item?.simbolo} é <strong>{nomeDoTipo(tipos, tipoOficial)}</strong>, não{" "}
          {tipo.nome}.{" "}
          <Button
            type="button"
            variant="link"
            className="h-auto p-0"
            onClick={() => {
              aoTrocarTipo(tipoOficial, escolha);
            }}
          >
            Usar {nomeDoTipo(tipos, tipoOficial)}
          </Button>
        </Aviso>
      )}
      {item?.origem === "pesquisa" && item.tipo === null && (
        <Aviso>
          Tipo não identificado: {item.simbolo} não está na lista oficial. Confira se ele é mesmo{" "}
          {tipo.nome}.
        </Aviso>
      )}
      {escolha.origem === "manual" && (
        <Aviso>
          {escolha.simbolo} não foi encontrado nas listas oficiais: a cotação pode falhar. Confira o
          ticker e o tipo.
        </Aviso>
      )}
    </div>
  );
}

/** Venda, resgate e provento: só ativos com posição (provento: os demais do tipo também). */
function EscolhaDePosicao({
  form,
  tipo,
  ativos,
  operacao,
  instituicaoEscolhida,
  posicoes,
}: {
  form: Formulario;
  tipo: TipoAtivo;
  ativos: Ativo[];
  operacao: string;
  instituicaoEscolhida: boolean;
  posicoes: ReturnType<typeof usePosicoesNaData>;
}) {
  const ativoId = useWatch({ control: form.control, name: "ativo_id" });
  const erro = form.formState.errors.ativo_id?.message;
  if (!instituicaoEscolhida) {
    return (
      <p className="text-sm text-muted-foreground">
        Escolha a instituição para ver as posições de {tipo.nome}.
      </p>
    );
  }
  if (posicoes.isPending) return <Carregando />;
  if (posicoes.isError) {
    return (
      <EstadoErro
        erro={posicoes.error}
        aoTentarNovamente={() => {
          void posicoes.refetch();
        }}
      />
    );
  }
  const abertas = posicoes.data.filter((p) => p.tipo === tipo.slug);
  const comPosicao = new Set(abertas.map((p) => p.ativo_id));
  const outros =
    operacao === "provento"
      ? ativos.filter((a) => a.tipo === tipo.slug && !comPosicao.has(a.id))
      : [];
  if (abertas.length === 0 && outros.length === 0) {
    return (
      <Campo rotulo="Ativo" obrigatorio erro={erro}>
        <Select disabled value="">
          <option value="">Nenhuma posição de {tipo.nome} nesta instituição na data</option>
        </Select>
      </Campo>
    );
  }
  return (
    <Campo rotulo="Ativo" obrigatorio erro={erro}>
      <Select
        value={ativoId}
        onChange={(e) => {
          form.clearErrors("ativo_id");
          form.setValue("modo_ativo", e.target.value === "" ? "" : "existente");
          form.setValue("ativo_id", e.target.value);
        }}
      >
        <option value="">Escolha…</option>
        <optgroup label="Posições abertas">
          {abertas.map((p) => (
            <option key={p.ativo_id} value={p.ativo_id}>
              {p.simbolo ?? p.nome}
              {p.simbolo ? ` · ${p.nome}` : ""}
            </option>
          ))}
        </optgroup>
        {outros.length > 0 && (
          <optgroup label="Sem posição na data">
            {outros.map((a) => (
              <option key={a.id} value={a.id}>
                {rotuloAtivo(a)}
              </option>
            ))}
          </optgroup>
        )}
      </Select>
    </Campo>
  );
}

/** Dados do ativo novo, gerados a partir do schema do tipo (como no cadastro). */
function CamposNovoAtivo({
  form,
  tipo,
  escolha,
}: {
  form: Formulario;
  tipo: TipoAtivo;
  escolha: Escolha | null;
}) {
  const erros = form.formState.errors.novo_ativo;
  const daLista = escolha?.origem === "resultado";
  const campos = tipo.campos.filter((c) => !CAMPOS_COM_A_DATA_DA_OPERACAO.has(c.nome));
  return (
    <fieldset className="grid gap-4 rounded-lg border p-3 sm:col-span-2 sm:grid-cols-2">
      <legend className="px-1 text-sm font-medium">Novo ativo ({tipo.nome})</legend>
      {tipo.busca_por_ticker && (
        <Campo
          rotulo="Ticker"
          obrigatorio
          erro={erros?.simbolo?.message}
          ajuda={daLista ? "Vem da lista oficial." : undefined}
        >
          <Input {...form.register("novo_ativo.simbolo")} maxLength={30} readOnly={daLista} />
        </Campo>
      )}
      <Campo
        rotulo="Nome"
        obrigatorio
        erro={erros?.nome?.message}
        className={tipo.busca_por_ticker ? undefined : "sm:col-span-2"}
      >
        <Input {...form.register("novo_ativo.nome")} maxLength={150} />
      </Campo>
      {tipo.moedas_aceitas.length > 1 && (
        <Campo rotulo="Moeda" erro={erros?.moeda?.message}>
          <Select {...form.register("novo_ativo.moeda")}>
            {tipo.moedas_aceitas.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Campo>
      )}
      {tipo.provider && !tipo.busca_por_ticker && (
        <Campo
          rotulo="Símbolo na fonte de cotação"
          erro={erros?.simbolo_externo?.message}
          ajuda={AJUDA_SIMBOLO_EXTERNO[tipo.slug]}
        >
          <Input {...form.register("novo_ativo.simbolo_externo")} maxLength={60} />
        </Campo>
      )}
      {campos.map((campo) => (
        <Controller
          key={campo.nome}
          control={form.control}
          name={`novo_ativo.metadados.${campo.nome}`}
          render={({ field }) => (
            <Campo
              rotulo={campo.rotulo}
              obrigatorio={campo.obrigatorio}
              erro={erros?.metadados?.[campo.nome]?.message}
              ajuda={campo.ajuda ?? undefined}
            >
              {campo.tipo === "escolha" ? (
                <Select {...field}>
                  <option value="">{campo.obrigatorio ? "Escolha…" : "—"}</option>
                  {campo.opcoes.map((o) => (
                    <option key={o.valor} value={o.valor}>
                      {o.rotulo}
                    </option>
                  ))}
                </Select>
              ) : campo.tipo === "data" ? (
                <Input type="date" {...field} />
              ) : (
                <Input
                  {...field}
                  inputMode={campo.tipo === "texto" ? "text" : "decimal"}
                  maxLength={campo.tamanho_maximo ?? undefined}
                />
              )}
            </Campo>
          )}
        />
      ))}
    </fieldset>
  );
}

/** Quantidade/preço ou valor, taxas, provento e câmbio, com o disponível na venda/resgate. */
function CamposDaOperacao({
  form,
  tipo,
  moeda,
  posicao,
}: {
  form: Formulario;
  tipo: TipoAtivo;
  moeda: string;
  posicao: Posicao | undefined;
}) {
  const erros = form.formState.errors;
  const operacao = useWatch({ control: form.control, name: "tipo" });
  const quantidade = useWatch({ control: form.control, name: "quantidade" });
  const valor = useWatch({ control: form.control, name: "valor" });
  const disponivel = usaQuantidade(operacao) ? posicao?.quantidade : posicao?.valor;
  const digitado = normalizarDecimal(usaQuantidade(operacao) ? quantidade : valor);
  const acima =
    disponivel !== null &&
    disponivel !== undefined &&
    digitado !== null &&
    comparar(digitado, disponivel) > 0;
  const textoDisponivel =
    disponivel === null || disponivel === undefined
      ? undefined
      : usaQuantidade(operacao)
        ? `Disponível: ${formatarNumero(disponivel, { minimo: 0, maximo: 8 })}`
        : `Disponível: ${formatarMoeda(disponivel, moeda)} (estimado)`;
  const ajuda = acima ? (
    <span className="text-aviso-texto">
      {textoDisponivel}. Maior que a posição: o registro será recusado.
    </span>
  ) : (
    textoDisponivel
  );

  return (
    <>
      {usaQuantidade(operacao) ? (
        <>
          <Campo rotulo="Quantidade" obrigatorio erro={erros.quantidade?.message} ajuda={ajuda}>
            <Input inputMode="decimal" {...form.register("quantidade")} />
          </Campo>
          <Campo
            rotulo={`Preço unitário (${moeda})`}
            obrigatorio
            erro={erros.preco_unitario?.message}
          >
            <Input inputMode="decimal" {...form.register("preco_unitario")} />
          </Campo>
          {tipo.aceita_taxas && (
            <Campo rotulo={`Taxas (${moeda})`} erro={erros.taxas?.message}>
              <Input inputMode="decimal" placeholder="0,00" {...form.register("taxas")} />
            </Campo>
          )}
        </>
      ) : (
        <Campo
          rotulo={
            operacao === "provento" ? `Valor líquido recebido (${moeda})` : `Valor (${moeda})`
          }
          obrigatorio
          erro={erros.valor?.message}
          ajuda={operacao === "resgate" ? ajuda : undefined}
        >
          <Input inputMode="decimal" {...form.register("valor")} />
        </Campo>
      )}
      {operacao === "provento" && (
        <>
          <Campo rotulo="Tipo do provento" obrigatorio erro={erros.subtipo_provento?.message}>
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
            <Input inputMode="decimal" placeholder="0,00" {...form.register("imposto_retido")} />
          </Campo>
        </>
      )}
      {moeda !== "BRL" && (
        <Campo
          rotulo={`Câmbio pago (R$ por ${moeda})`}
          erro={erros.cambio?.message}
          ajuda="Opcional. Se vazio, usa a PTAX da data."
        >
          <Input inputMode="decimal" placeholder="ex.: 5,4321" {...form.register("cambio")} />
        </Campo>
      )}
    </>
  );
}

function Aviso({ children }: { children: React.ReactNode }) {
  return (
    <p role="status" className="flex items-start gap-2 text-xs text-aviso-texto">
      <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <span>{children}</span>
    </p>
  );
}
