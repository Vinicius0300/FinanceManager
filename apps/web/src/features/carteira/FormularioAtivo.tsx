import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useMemo } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import type { components } from "@/api/schema";
import { Campo } from "@/components/Campo";
import { MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import type { Ativo, TipoAtivo } from "@/lib/consultas-comuns";
import {
  AJUDA_SIMBOLO_EXTERNO,
  criarEsquemaAtivo,
  paraEntradaAtivo,
  type AtivoEntrada,
  type ValoresFormularioAtivo,
} from "./esquemaAtivo";
import { aplicarErrosDaApi, paraCampo } from "@/lib/formularios";

type CampoTipo = components["schemas"]["CampoTipo"];

/**
 * Formulário de ativo gerado a partir do schema do tipo: cada `CampoTipo` vira um controle.
 * Um tipo novo no registry aparece aqui sem mudar o front. Na edição, tipo, moeda e símbolo
 * ficam bloqueados (a API não permite trocá-los).
 */

function valoresIniciais(tipo: TipoAtivo, ativo?: Ativo): ValoresFormularioAtivo {
  const metadados = Object.fromEntries(
    tipo.campos.map((c) => {
      const atual: unknown = ativo?.metadados[c.nome];
      if (atual === undefined || atual === null) return [c.nome, ""];
      const texto = typeof atual === "string" ? atual : JSON.stringify(atual);
      return [c.nome, c.tipo === "decimal" ? paraCampo(texto) : texto];
    }),
  );
  return {
    nome: ativo?.nome ?? "",
    simbolo: ativo?.simbolo ?? "",
    moeda: ativo?.moeda ?? tipo.moeda_padrao,
    simbolo_externo: ativo?.simbolo_externo ?? "",
    metadados,
  };
}

export function FormularioAtivo({
  tipo,
  ativo,
  ocupado,
  erro,
  aoSalvar,
  aoCancelar,
}: {
  tipo: TipoAtivo;
  ativo?: Ativo;
  ocupado: boolean;
  erro: unknown;
  aoSalvar: (entrada: AtivoEntrada) => Promise<unknown>;
  aoCancelar: () => void;
}) {
  const esquema = useMemo(() => criarEsquemaAtivo(tipo), [tipo]);
  const edicao = ativo !== undefined;
  const form = useForm<
    ValoresFormularioAtivo,
    unknown,
    z.output<ReturnType<typeof criarEsquemaAtivo>>
  >({
    resolver: zodResolver(esquema),
    defaultValues: valoresIniciais(tipo, ativo),
  });
  const erros = form.formState.errors;
  const camposApi = [
    "nome",
    "simbolo",
    "moeda",
    "simbolo_externo",
    ...tipo.campos.map((c) => `metadados.${c.nome}`),
  ];
  const mapaApi = Object.fromEntries(tipo.campos.map((c) => [c.nome, `metadados.${c.nome}`]));
  const cotado = tipo.modo === "cotas";

  const enviar = form.handleSubmit(async (dados) => {
    try {
      await aoSalvar(paraEntradaAtivo(tipo, dados));
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, camposApi, mapaApi);
    }
  });

  return (
    <form
      noValidate
      onSubmit={(e) => {
        void enviar(e);
      }}
      className="grid gap-4"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo rotulo="Nome" obrigatorio erro={erros.nome?.message} className="sm:col-span-2">
          <Input {...form.register("nome")} maxLength={150} />
        </Campo>
        {cotado && (
          <Campo
            rotulo="Símbolo (ticker)"
            erro={erros.simbolo?.message}
            ajuda={edicao ? "O símbolo não pode ser alterado." : undefined}
          >
            <Input {...form.register("simbolo")} disabled={edicao} maxLength={30} />
          </Campo>
        )}
        <Campo
          rotulo="Moeda"
          erro={erros.moeda?.message}
          ajuda={edicao ? "A moeda não pode ser alterada." : undefined}
        >
          <Select {...form.register("moeda")} disabled={edicao || tipo.moedas_aceitas.length < 2}>
            {tipo.moedas_aceitas.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Campo>
        {tipo.provider && (
          <Campo
            rotulo="Símbolo na fonte de cotação"
            erro={erros.simbolo_externo?.message}
            ajuda={AJUDA_SIMBOLO_EXTERNO[tipo.slug]}
            className="sm:col-span-2"
          >
            <Input {...form.register("simbolo_externo")} maxLength={60} />
          </Campo>
        )}
        {tipo.campos.map((campo) => (
          <CampoGerado key={campo.nome} campo={campo} form={form} />
        ))}
      </div>
      <MensagemErro erro={erro} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={aoCancelar} disabled={ocupado}>
          Cancelar
        </Button>
        <Button type="submit" disabled={ocupado}>
          {ocupado && <Loader2 aria-hidden className="animate-spin" />}
          {edicao ? "Salvar alterações" : "Cadastrar ativo"}
        </Button>
      </div>
    </form>
  );
}

function CampoGerado({
  campo,
  form,
}: {
  campo: CampoTipo;
  form: ReturnType<
    typeof useForm<ValoresFormularioAtivo, unknown, z.output<ReturnType<typeof criarEsquemaAtivo>>>
  >;
}) {
  const caminho = `metadados.${campo.nome}` as const;
  const erro = form.formState.errors.metadados?.[campo.nome]?.message;
  return (
    <Controller
      control={form.control}
      name={caminho}
      render={({ field }) => (
        <Campo
          rotulo={campo.rotulo}
          obrigatorio={campo.obrigatorio}
          erro={erro}
          ajuda={campo.ajuda ?? undefined}
        >
          {campo.tipo === "escolha" ? (
            <Select {...field} value={field.value}>
              <option value="">{campo.obrigatorio ? "Escolha…" : "—"}</option>
              {campo.opcoes.map((o) => (
                <option key={o.valor} value={o.valor}>
                  {o.rotulo}
                </option>
              ))}
            </Select>
          ) : campo.tipo === "data" ? (
            <Input type="date" {...field} value={field.value} />
          ) : (
            <Input
              {...field}
              value={field.value}
              inputMode={campo.tipo === "texto" ? "text" : "decimal"}
              maxLength={campo.tamanho_maximo ?? undefined}
            />
          )}
        </Campo>
      )}
    />
  );
}
