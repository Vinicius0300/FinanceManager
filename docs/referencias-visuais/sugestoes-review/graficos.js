// Gráficos estáticos das maquetes (SVG gerado a partir de arrays; dados fictícios).
const NS = "http://www.w3.org/2000/svg";
const cor = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function largura(alvo, l) {
  return l === "auto" ? document.querySelector(alvo).clientWidth : l;
}
function svg(alvo, l, a) {
  l = largura(alvo, l);
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("width", l); s.setAttribute("height", a); s.setAttribute("viewBox", `0 0 ${l} ${a}`);
  document.querySelector(alvo).appendChild(s);
  return s;
}
function el(pai, nome, attrs, texto) {
  const e = document.createElementNS(NS, nome);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (texto !== undefined) e.textContent = texto;
  pai.appendChild(e);
  return e;
}
function grade(s, x0, y0, l, a, max, passos, fmt) {
  for (let i = 0; i <= passos; i++) {
    const y = y0 + a - (a * i) / passos;
    el(s, "line", { x1: x0, x2: x0 + l, y1: y, y2: y, stroke: cor("--border") });
    el(s, "text", { x: x0 - 6, y: y + 3, "text-anchor": "end" }, fmt((max * i) / passos));
  }
}
function eixoX(s, x0, y, l, rotulos) {
  rotulos.forEach((r, i) =>
    el(s, "text", { x: x0 + (l * i) / (rotulos.length - 1), y, "text-anchor": i === 0 ? "start" : i === rotulos.length - 1 ? "end" : "middle" }, r));
}

/** Áreas empilhadas: series = [{cor, valores}], de baixo para cima. */
function areasEmpilhadas(alvo, l, a, series, rotulos, fmt) {
  l = largura(alvo, l);
  const s = svg(alvo, l, a), x0 = 44, y0 = 8, w = l - x0 - 8, h = a - 30;
  const n = series[0].valores.length;
  const totais = Array.from({ length: n }, (_, i) => series.reduce((t, se) => t + se.valores[i], 0));
  const max = Math.ceil(Math.max(...totais) / 50) * 50;
  grade(s, x0, y0, w, h, max, 4, fmt);
  const base = new Array(n).fill(0);
  const px = (i) => x0 + (w * i) / (n - 1), py = (v) => y0 + h - (h * v) / max;
  for (const se of series) {
    const topo = se.valores.map((v, i) => base[i] + v);
    const ida = topo.map((v, i) => `${px(i)},${py(v)}`).join(" ");
    const volta = base.map((v, i) => `${px(i)},${py(v)}`).reverse().join(" ");
    el(s, "polygon", { points: `${ida} ${volta}`, fill: se.cor, "fill-opacity": 0.55 });
    el(s, "polyline", { points: ida, fill: "none", stroke: se.cor, "stroke-width": 1.6 });
    topo.forEach((v, i) => (base[i] = v));
  }
  eixoX(s, x0, a - 6, w, rotulos);
}

/** Barras agrupadas ou empilhadas: series = [{cor, valores}]. */
function barras(alvo, l, a, series, rotulos, fmt, { empilhar = false, linha = null } = {}) {
  l = largura(alvo, l);
  const s = svg(alvo, l, a), x0 = 44, y0 = 8, w = l - x0 - 8, h = a - 30;
  const n = rotulos.length;
  const alturas = Array.from({ length: n }, (_, i) =>
    empilhar ? series.reduce((t, se) => t + se.valores[i], 0) : Math.max(...series.map((se) => se.valores[i])));
  const max = Math.ceil(Math.max(...alturas, ...(linha ? linha.valores : [])) / 10) * 10;
  grade(s, x0, y0, w, h, max, 4, fmt);
  const faixa = w / n, py = (v) => y0 + h - (h * v) / max;
  rotulos.forEach((r, i) => {
    let base = 0;
    const lb = empilhar ? faixa * 0.56 : (faixa * 0.7) / series.length;
    series.forEach((se, j) => {
      const v = se.valores[i];
      const x = x0 + faixa * i + (empilhar ? faixa * 0.22 : faixa * 0.15 + lb * j);
      const yTopo = py(empilhar ? base + v : v), yBase = py(empilhar ? base : 0);
      el(s, "rect", { x, y: yTopo, width: lb - 2, height: Math.max(0, yBase - yTopo), rx: 3, fill: se.cor });
      if (empilhar) base += v;
    });
    el(s, "text", { x: x0 + faixa * (i + 0.5), y: a - 6, "text-anchor": "middle" }, r);
  });
  if (linha) {
    const pts = linha.valores.map((v, i) => `${x0 + faixa * (i + 0.5)},${py(v)}`).join(" ");
    el(s, "polyline", { points: pts, fill: "none", stroke: linha.cor, "stroke-width": 2.2 });
    linha.valores.forEach((v, i) =>
      el(s, "circle", { cx: x0 + faixa * (i + 0.5), cy: py(v), r: 3, fill: linha.cor }));
  }
}

/** Linha mínima para os cartões de métrica. */
function faisca(alvo, valores, corLinha) {
  const l = 120, a = 34, s = svg(alvo, l, a);
  const min = Math.min(...valores), max = Math.max(...valores);
  const pts = valores.map((v, i) => [(l * i) / (valores.length - 1), a - 3 - ((a - 6) * (v - min)) / (max - min || 1)]);
  el(s, "polygon", { points: `0,${a} ${pts.map((p) => p.join(",")).join(" ")} ${l},${a}`, fill: corLinha, "fill-opacity": 0.15 });
  el(s, "polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: corLinha, "stroke-width": 1.8 });
}

/** Mapa de árvore (fatias alternadas): itens = [{nome, valor, rent}] ordenados. */
function mapaArvore(alvo, l, a, itens) {
  l = largura(alvo, l);
  const s = svg(alvo, l, a);
  const corDe = (r) => {
    const t = Math.max(-1, Math.min(1, r / 30));
    const base = t >= 0 ? [52, 211, 153] : [255, 107, 129];
    const k = 0.25 + 0.75 * Math.abs(t);
    const fundo = [33, 31, 58];
    return `rgb(${base.map((c, i) => Math.round(fundo[i] + (c - fundo[i]) * k)).join(",")})`;
  };
  function dividir(lista, x, y, w, h, horizontal) {
    if (lista.length === 0) return;
    if (lista.length === 1) {
      const it = lista[0];
      el(s, "rect", { x: x + 2, y: y + 2, width: w - 4, height: h - 4, rx: 8, fill: corDe(it.rent) });
      const t1 = el(s, "text", { x: x + 12, y: y + 24, "font-size": w > 150 ? 15 : 12, "font-weight": 700 }, it.nome);
      t1.style.fill = "#0e0d1f";
      const t2 = el(s, "text", { x: x + 12, y: y + 42, "font-size": 11.5, "font-weight": 600 },
        `${it.rent >= 0 ? "+" : "−"}${Math.abs(it.rent).toFixed(1).replace(".", ",")}%`);
      t2.style.fill = "#0e0d1f";
      if (h > 70) { const t3 = el(s, "text", { x: x + 12, y: y + h - 12, "font-size": 11 }, it.rotulo); t3.style.fill = "#0e0d1f"; }
      return;
    }
    const total = lista.reduce((t, i) => t + i.valor, 0);
    let soma = 0, corte = 0;
    while (soma < total / 2 && corte < lista.length - 1) soma += lista[corte++].valor;
    const fr = soma / total, a1 = lista.slice(0, corte), a2 = lista.slice(corte);
    if (horizontal) { dividir(a1, x, y, w * fr, h, !horizontal); dividir(a2, x + w * fr, y, w * (1 - fr), h, !horizontal); }
    else { dividir(a1, x, y, w, h * fr, !horizontal); dividir(a2, x, y + h * fr, w, h * (1 - fr), !horizontal); }
  }
  dividir(itens, 0, 0, l, a, true);
}

/** Barras horizontais com rótulo e valor (ex.: yield on cost). */
function barrasHorizontais(alvo, l, itens, corBarra) {
  l = largura(alvo, l);
  const a = itens.length * 30 + 6, s = svg(alvo, l, a);
  const max = Math.max(...itens.map((i) => i.v));
  itens.forEach((it, i) => {
    const y = 6 + i * 30;
    el(s, "text", { x: 0, y: y + 14, "font-size": 12 }, it.nome).style.fill = cor("--foreground");
    el(s, "rect", { x: 70, y: y + 3, width: l - 140, height: 14, rx: 7, fill: cor("--muted") });
    el(s, "rect", { x: 70, y: y + 3, width: ((l - 140) * it.v) / max, height: 14, rx: 7, fill: corBarra });
    el(s, "text", { x: l, y: y + 14, "text-anchor": "end", "font-size": 12, "font-weight": 700 }, it.r).style.fill = cor("--foreground");
  });
}
