import { BookOpen, Loader2 } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CabecalhoPagina, Secao } from "@/components/CabecalhoPagina";
import { CartaoMetrica } from "@/components/CartaoMetrica";
import { Carregando, EstadoErro, MensagemErro } from "@/components/Estados";
import { Segmentos } from "@/components/Segmentos";
import { Input, Label, Select } from "@/components/ui/input";
import { useAtivos, useTiposAtivo, type Ativo, type TipoAtivo } from "@/lib/consultas-comuns";
import { somar } from "@/lib/decimal";
import { formatarMoeda, formatarNumero, plural } from "@/lib/formatacao";
import { paraCampo } from "@/lib/formularios";
import { cn } from "@/lib/utils";
import { useValoresOcultos } from "@/lib/valores-ocultos";
import { erroDoAporte, lerAporte, lerModo, MODOS, TOLERANCIAS } from "./apresentacao";
import {
  useGravarMetas,
  useMetas,
  usePlano,
  type Metas,
  type ModoPlano,
  type Plano,
} from "./consultas";
import { EdicaoMetas } from "./EdicaoMetas";
import { GraficoAtualVsMeta } from "./GraficoAtualVsMeta";
import { PlanoAporte } from "./PlanoAporte";
import { TabelaDesvios } from "./TabelaDesvios";

const ESPERA_DIGITACAO_MS = 400;

/**
 * Rebalanceamento (Parte 10): desvio de cada classe em relação às metas do usuário, onde
 * aportar e, no modo completo, o que vender e comprar. Determinístico e informativo: o
 * plano vem do backend e o app nunca executa ordens. Vale para a carteira inteira.
 *
 * As metas são editadas na própria tabela "Desvio por classe" (lápis da coluna Meta); sem
 * metas, a tabela já abre em edição. Aporte e modo ficam na URL (`aporte`, `modo`); valor
 * inválido cai no padrão (o caixa e "só com aportes"). O aporte digitado vai ao backend
 * depois de ~400 ms sem digitar, e a tela mantém o plano anterior enquanto o novo chega.
 */
export function TelaRebalanceamento() {
  useValoresOcultos(); // redesenha ao alternar o modo privacidade
  const [params, setParams] = useSearchParams();
  const aporteUrl = lerAporte(params.get("aporte"));
  const modo = lerModo(params.get("modo"));
  const plano = usePlano(aporteUrl, modo);
  const metas = useMetas();
  const tipos = useTiposAtivo();
  const ativos = useAtivos();
  const [editando, setEditando] = useState(false);

  const mudarParametro = (nome: string, valor: string | null) => {
    setParams(
      (atuais) => {
        const novos = new URLSearchParams(atuais);
        if (valor === null) novos.delete(nome);
        else novos.set(nome, valor);
        return novos;
      },
      { replace: true },
    );
  };

  const cadastros =
    metas.data && tipos.data && ativos.data
      ? { metas: metas.data, tipos: tipos.data, ativos: ativos.data }
      : null;
  const errosCadastro = metas.error ?? tipos.error ?? ativos.error;

  return (
    <div className="flex flex-col gap-3.5">
      <CabecalhoPagina
        titulo="Rebalanceamento"
        acoes={
          <Link
            to="/glossario/rebalanceamento"
            className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <BookOpen aria-hidden className="size-4" />O que é rebalanceamento?
          </Link>
        }
      />
      {plano.isPending ? (
        <Carregando texto="Calculando o plano…" />
      ) : plano.isError ? (
        <EstadoErro
          erro={plano.error}
          tentando={plano.isFetching}
          aoTentarNovamente={() => {
            void plano.refetch();
          }}
        />
      ) : !plano.data.tem_metas ? (
        <Secao titulo="Defina suas metas de alocação">
          <p className="mb-3 max-w-3xl text-sm text-muted-foreground">
            Diga quanto da carteira você quer em cada classe (ex.: 35% em renda fixa, 25% em ações),
            somando 100%. Depois de salvar, a tela mostra o desvio de cada classe e como dividir o
            próximo aporte.
          </p>
          {cadastros ? (
            <EdicaoMetas
              {...cadastros}
              plano={plano.data}
              primeiraVez
              aoTerminar={() => {
                setEditando(false);
              }}
            />
          ) : errosCadastro ? (
            <MensagemErro erro={errosCadastro} />
          ) : (
            <Carregando />
          )}
        </Secao>
      ) : (
        <ConteudoPlano
          plano={plano.data}
          atualizando={plano.isFetching}
          aporteUrl={aporteUrl}
          modo={modo}
          aoMudarAporte={(valor) => {
            mudarParametro("aporte", valor);
          }}
          aoMudarModo={(valor) => {
            mudarParametro("modo", valor === "aportes" ? null : valor);
          }}
          cadastros={cadastros}
          tiposCarregados={tipos.data}
          editando={editando}
          aoMudarEdicao={setEditando}
        />
      )}
    </div>
  );
}

function ConteudoPlano({
  plano,
  atualizando,
  aporteUrl,
  modo,
  aoMudarAporte,
  aoMudarModo,
  cadastros,
  tiposCarregados,
  editando,
  aoMudarEdicao,
}: {
  plano: Plano;
  atualizando: boolean;
  aporteUrl: string | null;
  modo: ModoPlano;
  aoMudarAporte: (valor: string | null) => void;
  aoMudarModo: (valor: ModoPlano) => void;
  cadastros: { metas: Metas; tipos: readonly TipoAtivo[]; ativos: readonly Ativo[] } | null;
  tiposCarregados: readonly TipoAtivo[] | undefined;
  editando: boolean;
  aoMudarEdicao: (editando: boolean) => void;
}) {
  const somaMetas = somar(plano.classes.map((c) => c.meta ?? "0"));
  const comMeta = plano.classes.filter((c) => c.meta !== null).length;
  return (
    <>
      <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        <CartaoMetrica
          titulo="Patrimônio considerado"
          valor={formatarMoeda(plano.patrimonio_considerado)}
          apoio="Posições abertas, sem o caixa"
        />
        <CartaoMetrica
          titulo="Desvio total"
          valor={`${formatarNumero(plano.desvio_total_pp, { minimo: 2, maximo: 2 })} p.p.`}
          apoio="Quanto da carteira está fora do lugar (Σ |desvio| ÷ 2)"
        />
        <CartaoMetrica
          titulo="Classes fora da banda"
          valor={`${plano.classes_fora_da_banda} de ${comMeta}`}
          apoio={`Tolerância de ±${plano.tolerancia_pp} p.p. em torno da meta`}
        />
        <CartaoMetrica
          titulo="Soma das metas"
          valor={`${formatarNumero(somaMetas, { maximo: 2 })}%`}
          apoio={plural(comMeta, "classe com meta", "classes com meta")}
        />
      </div>
      <Controles
        plano={plano}
        aporteUrl={aporteUrl}
        modo={modo}
        atualizando={atualizando}
        aoMudarAporte={aoMudarAporte}
        aoMudarModo={aoMudarModo}
        metas={cadastros?.metas}
      />
      <div className="grid gap-3.5 xl:grid-cols-5">
        <Secao titulo={editando ? "Editar metas" : "Desvio por classe"} className="xl:col-span-3">
          {editando && cadastros ? (
            <EdicaoMetas
              {...cadastros}
              plano={plano}
              aoTerminar={() => {
                aoMudarEdicao(false);
              }}
            />
          ) : (
            <TabelaDesvios
              classes={plano.classes}
              tolerancia={plano.tolerancia_pp}
              tipos={tiposCarregados}
              aoEditar={
                cadastros
                  ? () => {
                      aoMudarEdicao(true);
                    }
                  : undefined
              }
            />
          )}
        </Secao>
        <Secao
          titulo={modo === "completo" ? "Rebalanceamento completo" : "Como dividir o aporte"}
          className="xl:col-span-2"
        >
          <PlanoAporte plano={plano} tipos={tiposCarregados} />
        </Secao>
      </div>
      <Secao titulo="Atual × meta">
        <GraficoAtualVsMeta classes={plano.classes} tipos={tiposCarregados} />
      </Secao>
    </>
  );
}

/**
 * Um controle da barra: rótulo, controle (sempre com a mesma altura) e uma linha de ajuda,
 * para os três grupos ficarem alinhados no topo, no controle e na ajuda.
 */
function GrupoControle({
  rotulo,
  idControle,
  ajuda,
  erro,
  className,
  children,
}: {
  rotulo: string;
  idControle?: string;
  ajuda: ReactNode;
  erro?: string | null;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      {idControle ? (
        <Label htmlFor={idControle}>{rotulo}</Label>
      ) : (
        <span className="text-sm leading-none font-medium">{rotulo}</span>
      )}
      {children}
      {erro ? (
        <p
          id={idControle ? `${idControle}-erro` : undefined}
          role="alert"
          className="text-xs text-negativo"
        >
          {erro}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">{ajuda}</p>
      )}
    </div>
  );
}

function Controles({
  plano,
  aporteUrl,
  modo,
  atualizando,
  aoMudarAporte,
  aoMudarModo,
  metas,
}: {
  plano: Plano;
  aporteUrl: string | null;
  modo: ModoPlano;
  atualizando: boolean;
  aoMudarAporte: (valor: string | null) => void;
  aoMudarModo: (valor: ModoPlano) => void;
  metas: Metas | undefined;
}) {
  const id = useId();
  const idAporte = `${id}-aporte`;
  const idTolerancia = `${id}-tolerancia`;
  // `null` = o usuário ainda não digitou: mostra o aporte da URL ou o caixa.
  const [texto, setTexto] = useState<string | null>(null);
  const exibido = texto ?? paraCampo(aporteUrl ?? plano.aporte);
  const erro = texto === null ? null : erroDoAporte(texto);
  const gravar = useGravarMetas();
  // Sempre a função mais recente, sem reiniciar a espera a cada nova renderização.
  const mudarAporte = useRef(aoMudarAporte);
  useEffect(() => {
    mudarAporte.current = aoMudarAporte;
  });

  useEffect(() => {
    if (texto === null) return;
    const espera = setTimeout(() => {
      if (texto.trim() === "") mudarAporte.current(null);
      else {
        const valor = lerAporte(texto);
        if (valor !== null && valor !== aporteUrl) mudarAporte.current(valor);
      }
    }, ESPERA_DIGITACAO_MS);
    return () => {
      clearTimeout(espera);
    };
  }, [texto, aporteUrl]);

  return (
    <Secao>
      <div className="grid items-start gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-[14rem_14rem_auto_1fr]">
        <GrupoControle
          rotulo="Aporte (R$)"
          idControle={idAporte}
          erro={erro}
          ajuda={`Caixa disponível: ${formatarMoeda(plano.caixa_disponivel)}`}
        >
          <Input
            id={idAporte}
            inputMode="decimal"
            placeholder="0,00"
            value={exibido}
            aria-invalid={erro ? true : undefined}
            aria-describedby={erro ? `${idAporte}-erro` : undefined}
            onChange={(e) => {
              setTexto(e.target.value);
            }}
          />
        </GrupoControle>
        <GrupoControle
          rotulo="Tolerância da banda"
          idControle={idTolerancia}
          ajuda="Fora da banda se |desvio| > tolerância"
        >
          <Select
            id={idTolerancia}
            value={String(plano.tolerancia_pp)}
            disabled={!metas || gravar.isPending}
            onChange={(e) => {
              if (!metas) return;
              gravar.mutate({ ...metas, tolerancia_pp: Number(e.target.value) });
            }}
          >
            {TOLERANCIAS.map((t) => (
              <option key={t} value={t}>
                ±{t} p.p.
              </option>
            ))}
          </Select>
        </GrupoControle>
        <GrupoControle
          rotulo="Modo"
          ajuda={modo === "completo" ? "Compra e vende até as metas" : "Só compra, nunca vende"}
        >
          <Segmentos
            rotulo="Modo do plano"
            opcoes={MODOS}
            valor={modo}
            aoMudar={aoMudarModo}
            className="h-9 w-fit [&>button]:px-3"
          />
        </GrupoControle>
        <div className="flex h-full items-center justify-end sm:col-span-2 lg:col-span-1">
          {atualizando && (
            <span role="status" className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 aria-hidden className="size-3.5 animate-spin" />
              Recalculando…
            </span>
          )}
        </div>
      </div>
      <MensagemErro erro={gravar.error} />
    </Secao>
  );
}
