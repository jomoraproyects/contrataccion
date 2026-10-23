(function () {
  "use strict";
  const source = document.getElementById("datos-indicadores");
  if (!source) return;
  const data = JSON.parse(source.textContent);
  const NS = "http://www.w3.org/2000/svg";
  const numbers = new Intl.NumberFormat("es-CO", {maximumFractionDigits: 1});
  const color = (index) => "var(--chart-c-" + index + ")";

  function node(tag, attributes, content) {
    const element = document.createElementNS(NS, tag);
    Object.entries(attributes || {}).forEach(([key, value]) => element.setAttribute(key, value));
    if (content !== undefined) element.textContent = content;
    return element;
  }
  function label(svg, x, y, content, extra) {
    const item = node("text", {x, y, class: "chart-label-text", ...extra}, content);
    svg.appendChild(item);
    return item;
  }
  function tip(element, content) {
    element.setAttribute("tabindex", "0");
    element.setAttribute("role", "img");
    element.setAttribute("aria-label", content);
    element.appendChild(node("title", {}, content));
  }
  function canvas(container, width, height) {
    container.replaceChildren();
    const svg = node("svg", {viewBox: "0 0 " + width + " " + height, class: "analytics-svg", role: "group", "aria-label": container.getAttribute("aria-label")});
    container.appendChild(svg);
    return svg;
  }
  function empty(container, message) {
    container.replaceChildren();
    const text = document.createElement("p");
    text.className = "analytics-chart-empty";
    text.textContent = message || "No hay candidatos para estos filtros.";
    container.appendChild(text);
  }
  function maxAxis(value) {
    const raw = Math.max(1, value) / 4;
    const power = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 5, 10].find((x) => x * power >= raw) * power;
    return Math.max(1, Math.ceil(value / step) * step);
  }

  function donut() {
    const container = document.querySelector('[data-chart="estados"]');
    const legend = document.querySelector("[data-chart-legend]");
    if (!data.total) { empty(container); return; }
    const svg = canvas(container, 260, 250);
    const radius = 88, circumference = 2 * Math.PI * radius;
    svg.appendChild(node("circle", {cx: 130, cy: 122, r: radius, fill: "none", stroke: "var(--app-border)", "stroke-width": 28}));
    let start = 0;
    data.estados.forEach((item, i) => {
      const fraction = item.cantidad / data.total;
      if (item.cantidad) {
        const arc = node("circle", {cx: 130, cy: 122, r: radius, fill: "none", stroke: color(i), "stroke-width": 28,
          "stroke-dasharray": (fraction * circumference) + " " + circumference, "stroke-dashoffset": -start * circumference, transform: "rotate(-90 130 122)"});
        tip(arc, item.etiqueta + ": " + item.cantidad + " (" + numbers.format(fraction * 100) + "%)");
        svg.appendChild(arc);
      }
      start += fraction;
      const li = document.createElement("li");
      const dot = document.createElement("span"); dot.className = "analytics-legend-dot chart-color-" + i;
      const name = document.createElement("span"); name.textContent = item.etiqueta;
      const value = document.createElement("strong"); value.textContent = item.cantidad;
      const percentage = document.createElement("small"); percentage.textContent = numbers.format(fraction * 100) + "%";
      li.append(dot, name, value, percentage); legend.appendChild(li);
    });
    label(svg, 130, 122, numbers.format(data.total), {"text-anchor": "middle", class: "chart-total"});
    label(svg, 130, 147, "candidatos", {"text-anchor": "middle"});
  }

  function vacancyBars() {
    const container = document.querySelector('[data-chart="vacantes"]');
    if (!data.vacantes.length) { empty(container); return; }
    const svg = canvas(container, 600, 282);
    const max = Math.max(...data.vacantes.map((x) => x.cantidad), 1);
    data.vacantes.forEach((item, i) => {
      const y = 18 + i * 51;
      const group = node("g"); tip(group, item.etiqueta + ": " + item.cantidad + " candidatos");
      const name = item.etiqueta.length > 24 ? item.etiqueta.slice(0, 23) + "…" : item.etiqueta;
      group.appendChild(node("text", {x: 0, y: y + 18, class: "chart-label-text"}, name));
      group.appendChild(node("rect", {x: 220, y, width: 320, height: 26, rx: 7, class: "chart-track"}));
      group.appendChild(node("rect", {x: 220, y, width: Math.max(3, item.cantidad / max * 320), height: 26, rx: 7, fill: color(i % 4)}));
      group.appendChild(node("text", {x: 556, y: y + 19, class: "chart-value-text"}, item.cantidad));
      svg.appendChild(group);
    });
  }

  function trend() {
    const container = document.querySelector('[data-chart="tendencia"]');
    if (!data.total || !data.tendencia.length) { empty(container); return; }
    const svg = canvas(container, 1100, 275);
    const left = 48, right = 1065, top = 16, bottom = 220;
    const approximateMaximum = maxAxis(Math.max(...data.tendencia.map((x) => x.cantidad)));
    const ticks = Math.min(4, approximateMaximum);
    const maximum = Math.ceil(approximateMaximum / ticks) * ticks;
    for (let i = 0; i <= ticks; i++) {
      const value = maximum * i / ticks, y = bottom - (bottom - top) * i / ticks;
      svg.appendChild(node("line", {x1: left, x2: right, y1: y, y2: y, class: "chart-grid-line"}));
      label(svg, left - 12, y + 5, numbers.format(value), {"text-anchor": "end"});
    }
    const points = data.tendencia.map((item, i) => ({
      ...item, x: data.tendencia.length === 1 ? (left + right) / 2 : left + i * (right - left) / (data.tendencia.length - 1),
      y: bottom - item.cantidad / maximum * (bottom - top),
    }));
    if (points.length > 1) {
      const path = points.map((p, i) => (i ? "L" : "M") + p.x + " " + p.y).join(" ");
      svg.appendChild(node("path", {d: path + " L" + points[points.length - 1].x + " " + bottom + " L" + points[0].x + " " + bottom + " Z", class: "chart-trend-area"}));
      svg.appendChild(node("path", {d: path, class: "chart-trend-line"}));
    }
    points.forEach((p, index) => {
      const circle = node("circle", {cx: p.x, cy: p.y, r: 6, class: "chart-trend-point"});
      tip(circle, p.etiqueta + ": " + p.cantidad + " candidatos");
      svg.appendChild(circle);
      label(svg, p.x, Math.max(14, p.y - 14), p.cantidad, {"text-anchor": "middle", class: "chart-value-text"});
      if (index % Math.ceil(points.length / 12) === 0 || index === points.length - 1) {
        label(svg, p.x, bottom + 29, p.etiqueta, {"text-anchor": "middle"});
      }
    });
  }

  function stageName(item) { return item.valor === "SEGURIDAD" ? "Seguridad y Salud" : item.etapa; }
  function stages(measure) {
    const container = document.querySelector('[data-chart="etapas"]');
    if (!data.etapas.some((item) => item.finalizadas)) { empty(container, "Aún no hay etapas finalizadas para medir tiempos."); return; }
    const svg = canvas(container, 600, 282), left = 188, width = 340;
    const maximum = maxAxis(Math.max(...data.etapas.map((x) => Math.max(x[measure] || 0, x.plazo_horas))));
    data.etapas.forEach((item, i) => {
      const y = 14 + i * 57;
      label(svg, 0, y + 20, stageName(item));
      svg.appendChild(node("rect", {x: left, y, width, height: 27, rx: 6, class: "chart-track"}));
      const group = node("g");
      if (item[measure] !== null) {
        const bar = node("rect", {x: left, y, width: Math.max(2, item[measure] / maximum * width), height: 27, rx: 6, fill: color(item[measure] > item.plazo_horas ? 3 : 0)});
        group.appendChild(bar);
        label(svg, left + width + 12, y + 20, numbers.format(item[measure]) + " h", {class: "chart-value-text"});
      } else { label(svg, left + 10, y + 19, "Sin datos"); }
      const limit = left + item.plazo_horas / maximum * width;
      group.appendChild(node("line", {x1: limit, x2: limit, y1: y - 4, y2: y + 31, class: "chart-limit-line"}));
      tip(group, item.etapa + ": " + (item[measure] === null ? "sin datos" : numbers.format(item[measure]) + " horas") + ". Plazo: " + item.plazo_dias + " días hábiles (" + item.plazo_horas + " horas).");
      svg.appendChild(group);
    });
    label(svg, left, 269, "0 h"); label(svg, left + width, 269, maximum + " h", {"text-anchor": "end"});
  }

  function compliance() {
    const container = document.querySelector('[data-chart="cumplimiento"]');
    if (!data.etapas.some((item) => item.finalizadas)) { empty(container, "Aún no hay etapas finalizadas para evaluar plazos."); return; }
    const svg = canvas(container, 600, 282), left = 188, width = 328;
    data.etapas.forEach((item, i) => {
      const y = 14 + i * 57;
      label(svg, 0, y + 20, stageName(item));
      svg.appendChild(node("rect", {x: left, y, width, height: 27, rx: 6, class: "chart-track"}));
      if (!item.finalizadas) { label(svg, left + 10, y + 19, "Sin datos"); return; }
      const good = item.a_tiempo / item.finalizadas * width;
      const group = node("g"); tip(group, item.etapa + ": " + item.a_tiempo + " a tiempo, " + item.retrasos_cerrados + " fuera de plazo. Cumplimiento: " + item.cumplimiento_porcentaje + "%.");
      if (good) group.appendChild(node("rect", {x: left, y, width: good, height: 27, fill: color(2)}));
      if (good < width) group.appendChild(node("rect", {x: left + good, y, width: width - good, height: 27, fill: color(3)}));
      svg.appendChild(group);
      label(svg, left + width + 12, y + 20, item.cumplimiento_porcentaje + "%", {class: "chart-value-text"});
    });
    label(svg, left, 269, "0%"); label(svg, left + width, 269, "100%", {"text-anchor": "end"});
  }

  donut(); vacancyBars(); trend(); stages("promedio_horas"); compliance();
  document.querySelector("[data-stage-measure]").addEventListener("change", (event) => stages(event.target.value));

  const form = document.querySelector("[data-analytics-filters]");
  function actualizarPeriodo() {
    const tipo = form.elements.periodo.value;
    document.querySelectorAll("[data-period-input]").forEach((wrapper) => {
      wrapper.hidden = wrapper.dataset.periodInput !== tipo;
      wrapper.querySelector("input").disabled = wrapper.hidden;
    });
    document.querySelector("[data-period-help]").textContent = {
      semanal: "Seleccione la semana. El informe incluye desde el lunes hasta el domingo.",
      mensual: "Seleccione el mes. El informe incluye desde el primer día hasta el último.",
      anual: "Seleccione el año. El informe incluye desde el 1 de enero hasta el 31 de diciembre.",
    }[tipo];
  }
  actualizarPeriodo();
  form.elements.periodo.addEventListener("change", actualizarPeriodo);
})();
