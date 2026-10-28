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

  function donut(kind, items, caption, legendSelector) {
    const container = document.querySelector('[data-chart="' + kind + '"]');
    const legend = document.querySelector(legendSelector);
    if (!container || !legend) return;
    legend.replaceChildren();
    const total = items.reduce((sum, item) => sum + item.cantidad, 0);
    if (!total) { empty(container, kind === "rechazos" ? "No hay candidatos rechazados con estos filtros." : undefined); return; }
    const svg = canvas(container, 260, 250);
    const radius = 88, circumference = 2 * Math.PI * radius;
    svg.appendChild(node("circle", {cx: 130, cy: 122, r: radius, fill: "none", stroke: "var(--app-border)", "stroke-width": 28}));
    let start = 0;
    items.forEach((item, i) => {
      const fraction = item.cantidad / total;
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
    label(svg, 130, 122, numbers.format(total), {"text-anchor": "middle", class: "chart-total"});
    label(svg, 130, 147, caption, {"text-anchor": "middle"});
  }

  function history() {
    const container = document.querySelector('[data-chart="historico"]');
    if (!container) return;
    const chart = data.historico;
    if (!chart || chart.error || !chart.filas.length) { empty(container, chart && chart.error || "No hay datos para construir el histórico."); return; }
    const series = [["recibidos", "Recibidos", 0], ["contratados", "Contratados", 2], ["rechazados", "Rechazados", 3]];
    const width = Math.max(680, chart.filas.length * 78 + 75);
    const svg = canvas(container, width, 300);
    svg.setAttribute("width", width); svg.setAttribute("height", 300);
    const left = 42, bottom = 240, top = 20, plot = width - 66;
    const approximateMaximum = maxAxis(Math.max(1, ...chart.filas.flatMap((item) => series.map(([key]) => item[key]))));
    const ticks = Math.min(4, approximateMaximum);
    const maximum = Math.ceil(approximateMaximum / ticks) * ticks;
    for (let i = 0; i <= ticks; i++) {
      const value = maximum * i / ticks, y = bottom - (bottom - top) * i / ticks;
      svg.appendChild(node("line", {x1: left, x2: width - 24, y1: y, y2: y, class: "chart-grid-line"}));
      label(svg, left - 9, y + 4, numbers.format(value), {"text-anchor": "end"});
    }
    const group = plot / chart.filas.length;
    const barWidth = Math.min(18, group / 5);
    chart.filas.forEach((item, i) => {
      const center = left + group * (i + .5);
      series.forEach(([key, title, index], j) => {
        const value = item[key], height = value / maximum * (bottom - top);
        const x = center + (j - 1.5) * (barWidth + 2);
        const bar = node("rect", {x, y: bottom - height, width: barWidth, height, rx: 3, fill: color(index)});
        tip(bar, item.etiqueta + ". " + title + ": " + value);
        svg.appendChild(bar);
        if (value) label(svg, x + barWidth / 2, bottom - height - 7, numbers.format(value), {"text-anchor": "middle", class: "chart-value-text"});
      });
      const parts = item.etiqueta.split(" · ");
      parts.forEach((part, j) => label(svg, center, bottom + 22 + j * 16, part, {"text-anchor": "middle"}));
    });
  }

  function vacancyBars() {
    const container = document.querySelector('[data-chart="vacantes"]');
    if (!data.vacantes.length) { empty(container); return; }
    container.replaceChildren();
    const list = document.createElement("ol");
    list.className = "vacancy-ranking";
    const max = Math.max(...data.vacantes.map((x) => x.cantidad), 1);
    data.vacantes.forEach((item, i) => {
      const row = document.createElement("li");
      const heading = document.createElement("div"); heading.className = "vacancy-ranking-heading";
      const name = document.createElement("span"); name.textContent = item.etiqueta;
      const count = document.createElement("strong"); count.textContent = numbers.format(item.cantidad);
      heading.append(name, count);
      const bar = node("svg", {viewBox: "0 0 100 8", preserveAspectRatio: "none", "aria-hidden": "true", focusable: "false", class: "vacancy-ranking-bar"});
      bar.appendChild(node("rect", {width: 100, height: 8, rx: 2, class: "chart-track"}));
      bar.appendChild(node("rect", {width: Math.max(0, item.cantidad / max * 100), height: 8, rx: 2, fill: color(i % 4)}));
      row.append(heading, bar); list.appendChild(row);
    });
    container.appendChild(list);
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

  donut("estados", data.estados, "candidatos", "[data-chart-legend]");
  donut("rechazos", data.rechazos || [], "rechazados", "[data-rejection-legend]");
  history(); vacancyBars(); stages("mediana_horas"); compliance();
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
      personalizado: "Seleccione desde qué fecha y hasta qué fecha desea consultar (ambas incluidas).",
    }[tipo];
  }
  actualizarPeriodo();
  form.elements.periodo.addEventListener("change", actualizarPeriodo);
})();
