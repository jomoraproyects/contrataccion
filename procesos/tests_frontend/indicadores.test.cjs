const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.textContent = ""; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || ""; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener() {}
}

function render(vacantes, extra = {}, all = false) {
  const source = new Element("script");
  source.textContent = JSON.stringify({ total: vacantes.length ? 8 : 0, estados: [], vacantes, etapas: [], ...extra });
  const selectors = Object.fromEntries([
    '[data-chart="estados"]', '[data-chart="vacantes"]', '[data-chart="etapas"]',
    '[data-chart="cumplimiento"]', '[data-chart-legend]', '[data-stage-measure]',
    '[data-analytics-filters]', '[data-period-help]',
    '[data-chart="historico"]', '[data-chart="rechazos"]', '[data-rejection-legend]',
  ].map((selector) => [selector, new Element("div")]));
  selectors['[data-analytics-filters]'].elements = {periodo: Object.assign(new Element("select"), {value: "mensual"})};
  const document = {
    getElementById: () => source,
    createElement: (tag) => new Element(tag),
    createElementNS: (_, tag) => new Element(tag),
    querySelector: (selector) => {
      assert.notEqual(selector, '[data-chart="tendencia"]', "No debe intentar dibujar el gráfico retirado");
      return selectors[selector];
    },
    querySelectorAll: () => [],
  };
  const script = fs.readFileSync(path.join(__dirname, "../../static/js/indicadores.js"), "utf8");
  vm.runInNewContext(script, {document, Intl});
  return all ? selectors : selectors['[data-chart="vacantes"]'];
}

test("nombres completos fuera del SVG, cantidades y barras proporcionales", () => {
  const nombre = "ASEO - RECOLECCION - HOSPITAL Y APOYO A OPERACIONES ESPECIALES";
  const ranking = render([{etiqueta: nombre, cantidad: 8}, {etiqueta: "ASEO - RECOLECCION - LUNES", cantidad: 2}]).children[0];
  assert.equal(ranking.tag, "ol");
  assert.equal(ranking.children[0].children[0].children[0].textContent, nombre);
  assert.equal(ranking.children[0].children[0].children[1].textContent, "8");
  assert.equal(ranking.children[0].children[1].children[1].attributes.width, "100");
  assert.equal(ranking.children[1].children[1].children[1].attributes.width, "25");
  assert.equal(ranking.children[0].children[1].children.some((child) => child.tag === "text"), false);
});

test("etiquetas se escriben como texto, nunca como HTML", () => {
  const nombre = '<img src=x onerror="alert(1)">';
  const ranking = render([{etiqueta: nombre, cantidad: 1}]).children[0];
  const etiqueta = ranking.children[0].children[0].children[0];
  assert.equal(etiqueta.tag, "span");
  assert.equal(etiqueta.textContent, nombre);
  assert.equal(etiqueta.children.length, 0);
});

test("periodo sin candidatos conserva estado vacío sin errores", () => {
  assert.match(render([]).children[0].textContent, /No hay candidatos/);
});

test("dona de rechazos muestra su propio total, sin confundirlo con todos los candidatos", () => {
  const selectores = render([], {total: 20, rechazos: [{etiqueta: "Psicología", cantidad: 2}, {etiqueta: "SST", cantidad: 3}]}, true);
  const svg = selectores['[data-chart="rechazos"]'].children[0];
  assert.equal(svg.tag, "svg");
  assert.equal(svg.children.filter((c) => c.attributes.class === "chart-total")[0].textContent, "5");
  const leyenda = selectores['[data-rejection-legend]'].children;
  assert.equal(leyenda[0].children[3].textContent, "40%");
  assert.equal(leyenda[1].children[3].textContent, "60%");
});

test("histórico agrupa tres series con escala compartida y sin falsear los ceros", () => {
  const selectores = render([], {historico: {filas: [{etiqueta: "09/2026", recibidos: 8, contratados: 4, rechazados: 0}, {etiqueta: "10/2026", recibidos: 4, contratados: 2, rechazados: 1}]}}, true);
  const svg = selectores['[data-chart="historico"]'].children[0];
  const barras = svg.children.filter(c => c.tag === "rect");
  assert.equal(barras.length, 6);
  assert.equal(Number(barras[0].attributes.height), Number(barras[1].attributes.height) * 2);
  assert.equal(Number(barras[2].attributes.height), 0);
  assert.equal(barras[2].attributes['aria-label'], "09/2026. Rechazados: 0");
});

test("histórico informa rangos excesivos sin romper las otras gráficas", () => {
  const selectores = render([], {historico: {filas: [], error: "Agrupe por año"}}, true);
  assert.equal(selectores['[data-chart="historico"]'].children[0].textContent, "Agrupe por año");
});
