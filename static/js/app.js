(function () {
  "use strict";

  const root = document.documentElement;

  function temaActual() {
    return root.dataset.bsTheme === "dark" ? "dark" : "light";
  }

  function actualizarBotonesTema() {
    const oscuro = temaActual() === "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach((boton) => {
      boton.setAttribute("aria-label", oscuro ? "Activar modo claro" : "Activar modo oscuro");
      boton.setAttribute("title", oscuro ? "Activar modo claro" : "Activar modo oscuro");
      const icono = boton.querySelector("[data-theme-icon]");
      if (icono) icono.textContent = oscuro ? "☀" : "☾";
    });
  }

  document.querySelectorAll("[data-theme-toggle]").forEach((boton) => {
    boton.addEventListener("click", function () {
      const nuevoTema = temaActual() === "dark" ? "light" : "dark";
      root.dataset.bsTheme = nuevoTema;
      try { localStorage.setItem("tema", nuevoTema); } catch (error) { /* Preferencia opcional. */ }
      document.cookie = "tema=" + nuevoTema + "; Max-Age=31536000; Path=/; SameSite=Lax";
      actualizarBotonesTema();
    });
  });
  actualizarBotonesTema();

  document.querySelectorAll("[data-password-toggle]").forEach((boton) => {
    boton.addEventListener("click", function () {
      const campo = document.getElementById(boton.getAttribute("aria-controls"));
      if (!campo) return;
      const mostrar = campo.type === "password";
      campo.type = mostrar ? "text" : "password";
      boton.textContent = mostrar ? "Ocultar" : "Mostrar";
      boton.setAttribute("aria-pressed", String(mostrar));
      campo.focus();
    });
  });

  document.querySelectorAll("form[data-submit-once]").forEach((formulario) => {
    formulario.addEventListener("submit", function () {
      const boton = formulario.querySelector('button[type="submit"]');
      if (!boton) return;
      window.setTimeout(function () {
        boton.disabled = true;
        const etiqueta = boton.querySelector("[data-submit-label]");
        if (etiqueta) etiqueta.textContent = boton.dataset.loadingText || "Guardando…";
      }, 0);
    });
  });

  const resumenError = document.querySelector("[data-error-summary]");
  if (resumenError) resumenError.focus();
})();
