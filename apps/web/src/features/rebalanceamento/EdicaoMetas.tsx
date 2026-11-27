import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronDown, ChevronRight, Loader2, Trash2 } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { DialogoConfirmacao } from "@/components/DialogoConfirmacao";
import { MensagemErro } from "@/components/Estados";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Ativo, TipoAtivo } from "@/lib/consultas-comuns";
import { formatarMoeda, formatarPercentual } from "@/lib/formatacao";
import { aplicarErrosDaApi } from "@/lib/formularios";
import { cn } from "@/lib/utils";
import { somarPercentuais } from "./apresentacao";
import { useGravarMetas, type Metas, type Plano } from "./consultas";
import {
  esquema,
  montarLinhas,
  paraCorpo,
  preenchido,
  type LinhaClasse,
  type Valores,
} from "./formularioMetas";

type Formulario = ReturnType<typeof useForm<Valores>>;

/**
 * Edição das metas dentro da tabela "Desvio por classe" (aberta pelo lápis da coluna Meta).
 * Todas as classes do registry viram linhas (as com posição primeiro), com o campo da meta
 * na coluna Meta; a classe que tem ativos se expande para os pesos deles. A soma aparece ao
 * vivo e o Salvar só libera com as classes (e os pesos de cada classe) somando 100%.
 *
 * `primeiraVez`: ainda não há metas. Não há o que cancelar nem apagar.
 */
export function EdicaoMetas({
  tipos,
  plano,
  metas,
  ativos,
  primeiraVez = false,
  aoTerminar,
}: {
  tipos: readonly TipoAtivo[];
  plano: Plano;
  metas: Metas;
  ativos: readonly Ativo[];
  primeiraVez?: boolean;
  aoTerminar: () => void;
}) {
  const gravar = useGravarMetas();
  const [confirmarApagar, setConfirmarApagar] = useState(false);
  const linhas = useMemo(
    () => montarLinhas(tipos, plano, metas, ativos),
    [tipos, plano, metas, ativos],
  );
  const form = useForm<Valores>({
    resolver: zodResolver(esquema),
    defaultValues: { classes: linhas },
  });
  const atuais = useWatch({ control: form.control, name: "classes" });
  const somaClasses = somarPercentuais(atuais.map((c) => c.percentual));
  const somasPesos = atuais.map((c) =>
    c.pesos.some((p) => preenchido(p.peso)) ? somarPercentuais(c.pesos.map((p) => p.peso)) : null,
  );
  const pesosOk = somasPesos.every((s) => s === null || s.completa);
  const errosRaiz = form.formState.errors.root as
    Record<string, { message?: string } | undefined> | undefined;

  // Campos da API → caminhos do formulário.
  const mapa: Record<string, string> = { classes: "root.soma" };
  linhas.forEach((linha, i) => {
    mapa[`classes.${linha.tipo}`] = `classes.${i}.percentual`;
    mapa[`pesos.${linha.tipo}`] = `root.pesos_${linha.tipo}`;
    linha.pesos.forEach((peso, j) => {
      mapa[`ativos.${peso.ativo_id}`] = `classes.${i}.pesos.${j}.peso`;
    });
  });

  const salvar = async (corpo: Metas) => {
    try {
      await gravar.mutateAsync(corpo);
      aoTerminar();
    } catch (falha) {
      aplicarErrosDaApi(falha, form.setError, Object.values(mapa), mapa);
    }
  };
  const enviar = form.handleSubmit((valores) => salvar(paraCorpo(valores, metas.tolerancia_pp)));

  return (
    <form
      noValidate
      aria-label="Editar metas de alocação"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        void enviar(e);
      }}
    >
      <Table aria-label="Metas de alocação por classe">
        <TableHeader>
          <TableRow>
            <TableHead>Classe</TableHead>
            <TableHead className="text-right">Valor atual</TableHead>
            <TableHead className="text-right">Atual</TableHead>
            <TableHead className="w-36 text-right">Meta (%)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {linhas.map((linha, i) => (
            <LinhasDaClasse
              key={linha.tipo}
              indice={i}
              linha={linha}
              plano={plano}
              form={form}
              somaPesos={somasPesos[i] ?? null}
              erroSomaPesos={errosRaiz?.[`pesos_${linha.tipo}`]?.message}
            />
          ))}
        </TableBody>
      </Table>
      <div className="flex flex-col gap-1">
        <p
          aria-live="polite"
          data-testid="soma-metas"
          className={cn(
            "text-sm font-semibold",
            somaClasses.completa ? "text-positivo" : "text-aviso-texto",
          )}
        >
          {somaClasses.texto}
        </p>
        {errosRaiz?.soma?.message && (
          <p role="alert" className="text-xs text-negativo">
            {errosRaiz.soma.message}
          </p>
        )}
        {!pesosOk && (
          <p className="text-xs text-aviso-texto">
            Os pesos de cada classe com pesos precisam somar 100%.
          </p>
        )}
      </div>
      <MensagemErro erro={gravar.error} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        {!primeiraVez && metas.classes.length > 0 ? (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setConfirmarApagar(true);
            }}
            disabled={gravar.isPending}
          >
            <Trash2 aria-hidden />
            Apagar todas as metas
          </Button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          {!primeiraVez && (
            <Button
              type="button"
              variant="outline"
              onClick={aoTerminar}
              disabled={gravar.isPending}
            >
              Cancelar
            </Button>
          )}
          <Button type="submit" disabled={gravar.isPending || !somaClasses.completa || !pesosOk}>
            {gravar.isPending && <Loader2 aria-hidden className="animate-spin" />}
            Salvar metas
          </Button>
        </div>
      </div>
      <DialogoConfirmacao
        aberto={confirmarApagar}
        aoMudar={setConfirmarApagar}
        titulo="Apagar todas as metas?"
        descricao="As metas das classes e os pesos dos ativos serão apagados. A tolerância continua a mesma."
        textoConfirmar="Apagar metas"
        ocupado={gravar.isPending}
        erro={gravar.error}
        aoConfirmar={() => {
          void salvar({ classes: [], ativos: [], tolerancia_pp: metas.tolerancia_pp }).then(() => {
            setConfirmarApagar(false);
          });
        }}
      />
    </form>
  );
}

function CampoPercentual({
  rotulo,
  erro,
  registro,
}: {
  rotulo: string;
  erro: string | undefined;
  registro: ReturnType<Formulario["register"]>;
}) {
  const idErro = `${registro.name}-erro`;
  return (
    <div className="flex flex-col items-end gap-1">
      <Input
        aria-label={rotulo}
        inputMode="decimal"
        placeholder="0"
        aria-invalid={erro ? true : undefined}
        aria-describedby={erro ? idErro : undefined}
        className="h-8 w-24 text-right"
        {...registro}
      />
      {erro && (
        <p id={idErro} role="alert" className="max-w-48 text-right text-xs text-negativo">
          {erro}
        </p>
      )}
    </div>
  );
}

function LinhasDaClasse({
  indice,
  linha,
  plano,
  form,
  somaPesos,
  erroSomaPesos,
}: {
  indice: number;
  linha: LinhaClasse;
  plano: Plano;
  form: Formulario;
  somaPesos: ReturnType<typeof somarPercentuais> | null;
  erroSomaPesos: string | undefined;
}) {
  const [aberta, setAberta] = useState(linha.pesos.some((p) => preenchido(p.peso)));
  const erros = form.formState.errors.classes?.[indice];
  const classe = plano.classes.find((c) => c.tipo_ativo === linha.tipo);
  return (
    <Fragment>
      <TableRow>
        <TableCell>
          {linha.pesos.length > 0 ? (
            <button
              type="button"
              aria-expanded={aberta}
              aria-label={`Pesos dos ativos de ${linha.nome}`}
              onClick={() => {
                setAberta(!aberta);
              }}
              className="inline-flex items-center gap-1 rounded-sm font-semibold hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {aberta ? (
                <ChevronDown aria-hidden className="size-3.5" />
              ) : (
                <ChevronRight aria-hidden className="size-3.5" />
              )}
              {linha.nome}
            </button>
          ) : (
            <span className={cn("font-semibold", !linha.temPosicao && "text-muted-foreground")}>
              {linha.nome}
            </span>
          )}
        </TableCell>
        <TableCell className="tabular text-right">
          {formatarMoeda(classe?.valor_atual ?? "0")}
        </TableCell>
        <TableCell className="tabular text-right">
          {formatarPercentual(classe?.percentual_atual ?? "0")}
        </TableCell>
        <TableCell className="text-right">
          <CampoPercentual
            rotulo={`Meta de ${linha.nome} (%)`}
            erro={erros?.percentual?.message}
            registro={form.register(`classes.${indice}.percentual`)}
          />
        </TableCell>
      </TableRow>
      {aberta && (
        <>
          {linha.pesos.map((peso, j) => {
            const item = classe?.ativos.find((a) => a.ativo_id === peso.ativo_id);
            return (
              <TableRow key={peso.ativo_id} className="bg-muted/40">
                <TableCell className="pl-8 font-medium">{peso.rotulo}</TableCell>
                <TableCell className="tabular text-right">
                  {formatarMoeda(item?.valor_atual ?? "0")}
                </TableCell>
                <TableCell className="text-right text-xs text-muted-foreground">
                  % da classe
                </TableCell>
                <TableCell className="text-right">
                  <CampoPercentual
                    rotulo={`Peso de ${peso.rotulo} (% da classe)`}
                    erro={erros?.pesos?.[j]?.peso?.message}
                    registro={form.register(`classes.${indice}.pesos.${j}.peso`)}
                  />
                </TableCell>
              </TableRow>
            );
          })}
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableCell colSpan={4} className="pl-8 text-xs">
              <span
                className={cn(
                  "font-semibold",
                  somaPesos === null
                    ? "text-muted-foreground"
                    : somaPesos.completa
                      ? "text-positivo"
                      : "text-aviso-texto",
                )}
              >
                {somaPesos === null
                  ? "Pesos opcionais: sem pesos, a sugestão fica só na classe."
                  : `Pesos — ${somaPesos.texto}`}
              </span>
              {erroSomaPesos && (
                <span role="alert" className="block text-negativo">
                  {erroSomaPesos}
                </span>
              )}
            </TableCell>
          </TableRow>
        </>
      )}
    </Fragment>
  );
}
