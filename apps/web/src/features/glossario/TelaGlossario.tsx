import { Info, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CabecalhoPagina, Secao } from "@/components/CabecalhoPagina";
import { EstadoVazio } from "@/components/Estados";
import { Segmentos } from "@/components/Segmentos";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { GLOSSARIO } from "./conteudo/glossario";
import { buscarTermos } from "./dominio/busca";
import { CATEGORIAS, tokenCategoria, type IdCategoria } from "./dominio/categorias";
import type { IndiceGlossario } from "./dominio/indice";
import { ROTA_GLOSSARIO, rotaDoTermo } from "./dominio/links";
import { GrafoGlossario } from "./GrafoGlossario";
import { termosVisiveis } from "./grafo";
import { ListaTermos } from "./ListaTermos";
import { MarcadorCategoria, Verbete } from "./Verbete";

const AVISO_GLOSSARIO =
  "Conteúdo educativo e simplificado. Não é recomendação de investimento. Regras de impostos mudam: confira a data de revisão de cada termo.";

/** Termos sugeridos na abertura (os que não existirem no conteúdo são ignorados). */
const SUGESTOES_INICIAIS = ["inflacao", "selic", "cdi", "juros-compostos", "diversificacao"];

type Visualizacao = "grafo" | "lista";

const OPCOES_VISUALIZACAO = [
  { valor: "grafo", rotulo: "Grafo" },
  { valor: "lista", rotulo: "Lista de termos" },
] as const satisfies readonly { valor: Visualizacao; rotulo: string }[];

function BoasVindas({ indice }: { indice: IndiceGlossario }) {
  const sugestoes = SUGESTOES_INICIAIS.map((s) => indice.porSlug.get(s)).filter(
    (t) => t !== undefined,
  );
  return (
    <div className="space-y-3 text-sm">
      <h2 className="text-lg font-bold">Como usar o glossário</h2>
      <p className="leading-relaxed text-muted-foreground">
        Cada bolinha do grafo é um termo, colorido pela categoria. As linhas mostram quais termos se
        relacionam, e as bolinhas maiores são os termos mais ligados; passe o mouse numa bolinha
        para ver as ligações dela. Clique numa bolinha, busque pelo nome ou troque para a Lista de
        termos para ler a explicação, com exemplo e ligações para os termos relacionados.
      </p>
      {sugestoes.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            Por onde começar
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {sugestoes.map((t) => (
              <li key={t.slug}>
                <Link
                  to={rotaDoTermo(t.slug)}
                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  <MarcadorCategoria categoria={t.categoria} className="size-2" />
                  {t.titulo}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Glossário (Parte 7): busca, filtro por categoria, o grafo de conhecimento **ou** a lista
 * de termos (o usuário escolhe) e, abaixo, o verbete aberto. Conteúdo fixo, embutido no app
 * (`conteudo/*.md`); o termo aberto vem da rota (`/glossario/:termo`), então voltar e
 * avançar do histórico funcionam.
 */
export function TelaGlossario({ indice = GLOSSARIO }: { indice?: IndiceGlossario }) {
  const { termo: slugAberto } = useParams();
  const navegar = useNavigate();
  const [busca, setBusca] = useState("");
  const [visualizacao, setVisualizacao] = useState<Visualizacao>("grafo");

  // Só as categorias que têm termos aparecem como filtro.
  const categoriasExistentes = useMemo(
    () => CATEGORIAS.filter((c) => indice.termos.some((t) => t.categoria === c.id)),
    [indice],
  );
  const [desligadas, setDesligadas] = useState<ReadonlySet<IdCategoria>>(new Set());
  const ativas = useMemo(
    () =>
      new Set<string>(categoriasExistentes.map((c) => c.id).filter((id) => !desligadas.has(id))),
    [categoriasExistentes, desligadas],
  );

  const termoAberto = slugAberto ? indice.porSlug.get(slugAberto) : undefined;
  const selecionado = termoAberto?.slug ?? null;

  const visiveis = useMemo(
    () => termosVisiveis(indice, ativas, selecionado),
    [indice, ativas, selecionado],
  );
  const resultado = useMemo(
    () => buscarTermos(indice.termos, busca).filter((t) => ativas.has(t.categoria)),
    [indice, busca, ativas],
  );
  const textoBusca = busca.trim();
  const primeiro = resultado[0];

  const alternarCategoria = (id: IdCategoria) => {
    setDesligadas((atual) => {
      const nova = new Set(atual);
      if (nova.has(id)) nova.delete(id);
      else nova.add(id);
      return nova;
    });
  };

  return (
    <div className="space-y-4">
      <CabecalhoPagina titulo="Glossário" />
      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <Info aria-hidden className="mt-px size-3.5 shrink-0" />
        {AVISO_GLOSSARIO}
      </p>

      <Secao>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[12rem] flex-1">
            <Search
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              type="search"
              aria-label="Buscar termo"
              placeholder="Buscar termo (ex.: CDI, inflação)"
              value={busca}
              onChange={(e) => {
                setBusca(e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && textoBusca && primeiro) {
                  e.preventDefault();
                  void navegar(rotaDoTermo(primeiro.slug));
                }
              }}
              className="pl-8"
            />
          </div>
          <Segmentos
            rotulo="Visualização"
            opcoes={OPCOES_VISUALIZACAO}
            valor={visualizacao}
            aoMudar={setVisualizacao}
          />
        </div>
        <div role="group" aria-label="Categorias" className="mb-2 flex flex-wrap gap-1.5">
          {categoriasExistentes.map((c) => {
            const ligada = !desligadas.has(c.id);
            return (
              <button
                key={c.id}
                type="button"
                aria-pressed={ligada}
                onClick={() => {
                  alternarCategoria(c.id);
                }}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50",
                  !ligada && "text-muted-foreground line-through opacity-60",
                )}
              >
                <span
                  aria-hidden
                  className="inline-block size-2.5 rounded-full"
                  style={{
                    backgroundColor: ligada ? tokenCategoria(c.id) : "transparent",
                    borderColor: tokenCategoria(c.id),
                    borderWidth: 1.5,
                  }}
                />
                {c.rotulo}
              </button>
            );
          })}
        </div>

        {visualizacao === "grafo" ? (
          <>
            {/* No grafo a busca não filtra o desenho: avisa quantos termos achou e como abri-los. */}
            {textoBusca && (
              <p role="status" className="mt-3 text-xs text-muted-foreground">
                {primeiro
                  ? `${String(resultado.length)} ${resultado.length === 1 ? "termo encontrado" : "termos encontrados"}. Aperte Enter para abrir “${primeiro.titulo}” ou veja todos em Lista de termos.`
                  : `Nenhum termo encontrado para “${textoBusca}”.`}
              </p>
            )}
            {visiveis.length === 0 ? (
              <EstadoVazio
                titulo="Nenhuma categoria selecionada"
                descricao="Ligue pelo menos uma categoria para ver os termos no grafo."
              />
            ) : (
              <GrafoGlossario indice={indice} visiveis={visiveis} selecionado={selecionado} />
            )}
          </>
        ) : (
          <div className="mt-3 space-y-2">
            {textoBusca && resultado.length > 0 && (
              <p role="status" className="text-xs text-muted-foreground">
                {`Resultado da busca: ${String(resultado.length)} ${resultado.length === 1 ? "termo" : "termos"}.`}
              </p>
            )}
            {resultado.length === 0 ? (
              <EstadoVazio
                titulo={
                  textoBusca
                    ? `Nenhum termo encontrado para “${textoBusca}”.`
                    : "Nenhum termo nas categorias selecionadas."
                }
                descricao={
                  textoBusca
                    ? "Tente outra palavra, um sinônimo ou ligue mais categorias."
                    : undefined
                }
              />
            ) : (
              <ListaTermos termos={resultado} />
            )}
          </div>
        )}
      </Secao>

      {/* O verbete fica abaixo do grafo (ou da lista) e ocupa a largura toda. */}
      <Secao>
        {termoAberto ? (
          <Verbete termo={termoAberto} indice={indice} />
        ) : slugAberto ? (
          <EstadoVazio
            titulo="Termo não encontrado"
            descricao={`Não há um termo “${slugAberto}” no glossário.`}
            acao={
              <Link
                to={ROTA_GLOSSARIO}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                Voltar ao início do glossário
              </Link>
            }
          />
        ) : (
          <BoasVindas indice={indice} />
        )}
      </Secao>
    </div>
  );
}
