import type { Aresta } from "./indice";

export interface Posicao {
  x: number;
  y: number;
}

/**
 * Estica o desenho na horizontal (ou na vertical) para a largura ficar `proporcao` vezes a
 * altura. O ECharts encaixa o grafo mantendo a proporção; sem isto, um desenho "em pé"
 * numa área larga ficaria espremido no meio, com as bolinhas umas sobre as outras.
 * Ex.: desenho de 100 × 100 com proporção 2 → 200 × 100 (só o x é multiplicado por 2).
 */
export function ajustarProporcao(
  posicoes: ReadonlyMap<string, Posicao>,
  proporcao: number,
): Map<string, Posicao> {
  const lista = [...posicoes.values()];
  if (lista.length < 2 || proporcao <= 0) return new Map(posicoes);
  const largura = Math.max(...lista.map((p) => p.x)) - Math.min(...lista.map((p) => p.x));
  const altura = Math.max(...lista.map((p) => p.y)) - Math.min(...lista.map((p) => p.y));
  if (largura <= 0 || altura <= 0) return new Map(posicoes);
  const fatorX = Math.max(1, (proporcao * altura) / largura);
  const fatorY = Math.max(1, largura / (proporcao * altura));
  return new Map(
    [...posicoes].map(([slug, { x, y }]) => [
      slug,
      { x: Math.round(x * fatorX * 10) / 10, y: Math.round(y * fatorY * 10) / 10 },
    ]),
  );
}

/** Gerador pseudoaleatório com semente (mulberry32): mesma entrada, mesmo desenho. */
function geradorComSemente(semente: number): () => number {
  let estado = semente >>> 0;
  return () => {
    estado = (estado + 0x6d2b79f5) >>> 0;
    let t = estado;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function sementeDe(slugs: readonly string[]): number {
  let h = 2166136261;
  for (const caractere of slugs.join("|")) {
    h ^= caractere.codePointAt(0) ?? 0;
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/**
 * Posições dos nós por força (Fruchterman-Reingold): nós se repelem, arestas puxam as
 * pontas, e uma gravidade leve segura componentes soltos perto do centro.
 *
 * A repulsão entre dois nós cresce com o número de ligações deles (ideia do ForceAtlas2,
 * do Gephi): termos muito ligados (CDI, Selic, CDB…) se afastam uns dos outros e abrem
 * espaço, em vez de se amontoarem no centro puxados pelas próprias ligações. O peso é
 * √((ligações de A + 1) × (ligações de B + 1)) ÷ (média de ligações + 1).
 *
 * Calculado aqui (e não pelo `layout: "force"` do ECharts) para o desenho ser **estável**:
 * o ECharts refaria a simulação a cada atualização das opções (destacar um termo, trocar o
 * tema), e as bolinhas pulariam de lugar. Com as posições prontas o grafo usa
 * `layout: "none"` e só muda quando o conjunto de nós muda. São ~50 nós: o custo é
 * desprezível (n² × iterações ≈ 750 mil operações).
 */
export function calcularPosicoes(
  slugs: readonly string[],
  arestas: readonly Aresta[],
  iteracoes = 300,
): Map<string, Posicao> {
  const n = slugs.length;
  const posicoes = new Map<string, Posicao>();
  if (n === 0) return posicoes;
  if (n === 1) {
    posicoes.set(slugs[0] ?? "", { x: 0, y: 0 });
    return posicoes;
  }

  const lado = 100 * Math.sqrt(n);
  const k = lado / Math.sqrt(n); // distância "ideal" entre nós
  const aleatorio = geradorComSemente(sementeDe(slugs));
  const x = slugs.map(() => (aleatorio() - 0.5) * lado);
  const y = slugs.map(() => (aleatorio() - 0.5) * lado);
  const indiceDe = new Map(slugs.map((s, i) => [s, i]));
  const pares = arestas
    .map(({ a, b }) => [indiceDe.get(a), indiceDe.get(b)] as const)
    .filter((p): p is readonly [number, number] => p[0] !== undefined && p[1] !== undefined);
  const graus = new Array<number>(n).fill(0);
  for (const [i, j] of pares) {
    graus[i] = (graus[i] ?? 0) + 1;
    graus[j] = (graus[j] ?? 0) + 1;
  }
  const grauMedio = (2 * pares.length) / n;

  const temperaturaInicial = lado / 8;
  for (let it = 0; it < iteracoes; it++) {
    const dx = new Array<number>(n).fill(0);
    const dy = new Array<number>(n).fill(0);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const ddx = (x[i] ?? 0) - (x[j] ?? 0);
        const ddy = (y[i] ?? 0) - (y[j] ?? 0);
        const dist = Math.max(Math.hypot(ddx, ddy), 0.01);
        const peso = Math.sqrt(((graus[i] ?? 0) + 1) * ((graus[j] ?? 0) + 1)) / (grauMedio + 1);
        const forca = (k * k * peso) / dist;
        dx[i] = (dx[i] ?? 0) + (ddx / dist) * forca;
        dy[i] = (dy[i] ?? 0) + (ddy / dist) * forca;
        dx[j] = (dx[j] ?? 0) - (ddx / dist) * forca;
        dy[j] = (dy[j] ?? 0) - (ddy / dist) * forca;
      }
    }
    for (const [i, j] of pares) {
      const ddx = (x[i] ?? 0) - (x[j] ?? 0);
      const ddy = (y[i] ?? 0) - (y[j] ?? 0);
      const dist = Math.max(Math.hypot(ddx, ddy), 0.01);
      const forca = (dist * dist) / k;
      dx[i] = (dx[i] ?? 0) - (ddx / dist) * forca;
      dy[i] = (dy[i] ?? 0) - (ddy / dist) * forca;
      dx[j] = (dx[j] ?? 0) + (ddx / dist) * forca;
      dy[j] = (dy[j] ?? 0) + (ddy / dist) * forca;
    }
    const temperatura = temperaturaInicial * (1 - it / iteracoes) + 0.5;
    for (let i = 0; i < n; i++) {
      // Gravidade proporcional à distância do centro.
      const gx = (dx[i] ?? 0) - 0.05 * k * ((x[i] ?? 0) / k);
      const gy = (dy[i] ?? 0) - 0.05 * k * ((y[i] ?? 0) / k);
      const desloc = Math.max(Math.hypot(gx, gy), 0.01);
      const passo = Math.min(desloc, temperatura);
      x[i] = (x[i] ?? 0) + (gx / desloc) * passo;
      y[i] = (y[i] ?? 0) + (gy / desloc) * passo;
    }
  }
  slugs.forEach((s, i) => {
    posicoes.set(s, { x: Math.round((x[i] ?? 0) * 10) / 10, y: Math.round((y[i] ?? 0) * 10) / 10 });
  });
  return posicoes;
}
