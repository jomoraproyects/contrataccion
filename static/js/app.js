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

  const modalConfirmacionElemento = document.getElementById("confirmationModal");
  const modalConfirmacion = modalConfirmacionElemento && window.bootstrap
    ? new bootstrap.Modal(modalConfirmacionElemento)
    : null;
  let formularioPorConfirmar = null;

  document.querySelectorAll("form[data-confirm-action]").forEach((formulario) => {
    formulario.addEventListener("submit", function (evento) {
      if (formulario.dataset.confirmed === "true" || !modalConfirmacion) return;
      if (formulario.dataset.confirmMode === "reject-only") {
        const resultado = formulario.querySelector('input[name="resultado"]:checked');
        if (!resultado || resultado.value !== "RECHAZADO") return;
      }
      evento.preventDefault();
      formularioPorConfirmar = formulario;
      modalConfirmacionElemento.querySelector("#confirmationModalTitle").textContent = formulario.dataset.confirmTitle || "Confirmar acción";
      modalConfirmacionElemento.querySelector("[data-confirm-message]").textContent = formulario.dataset.confirmMessage || "Revise la información antes de continuar.";
      modalConfirmacionElemento.querySelector("[data-confirm-subject]").textContent = formulario.dataset.confirmSubject || "—";
      modalConfirmacionElemento.querySelector("[data-confirm-stage]").textContent = formulario.dataset.confirmStage || "—";
      modalConfirmacion.show();
    });
  });

  const botonConfirmar = modalConfirmacionElemento && modalConfirmacionElemento.querySelector("[data-confirm-submit]");
  if (botonConfirmar) {
    botonConfirmar.addEventListener("click", function () {
      if (!formularioPorConfirmar) return;
      const formulario = formularioPorConfirmar;
      formularioPorConfirmar = null;
      formulario.dataset.confirmed = "true";
      modalConfirmacion.hide();
      formulario.requestSubmit();
    });
  }
  if (modalConfirmacionElemento) {
    modalConfirmacionElemento.addEventListener("hidden.bs.modal", function () {
      formularioPorConfirmar = null;
    });
  }

  document.querySelectorAll("form[data-submit-once]").forEach((formulario) => {
    formulario.addEventListener("submit", function (evento) {
      if (evento.defaultPrevented) return;
      const boton = formulario.querySelector('button[type="submit"]');
      if (!boton) return;
      window.setTimeout(function () {
        boton.disabled = true;
        const etiqueta = boton.querySelector("[data-submit-label]");
        if (etiqueta) etiqueta.textContent = boton.dataset.loadingText || "Guardando…";
      }, 0);
    });
  });

  const formularioCandidato = document.querySelector("form[data-candidate-lookup-url]");
  if (formularioCandidato) {
    const campoCedula = document.getElementById("id_cedula");
    const aviso = formularioCandidato.querySelector("[data-candidate-match]");
    const resumen = aviso.querySelector("[data-candidate-summary]");
    const rechazo = aviso.querySelector("[data-candidate-rejection]");
    const contextoRechazo = aviso.querySelector("[data-candidate-rejection-context]");
    const motivoRechazo = aviso.querySelector("[data-candidate-rejection-reason]");
    const botonCrear = formularioCandidato.querySelector('button[type="submit"]');
    let consultaActual = 0;
    let temporizadorConsulta;

    function limpiarAviso() {
      aviso.classList.add("d-none");
      aviso.classList.remove("alert-danger", "alert-info");
      rechazo.classList.add("d-none");
      resumen.textContent = "";
      contextoRechazo.textContent = "";
      motivoRechazo.textContent = "";
      botonCrear.disabled = false;
    }

    async function consultarCedula() {
      const cedula = (campoCedula.value || "").replace(/[.\s-]/g, "");
      const numeroConsulta = ++consultaActual;
      limpiarAviso();
      if (!/^\d{5,15}$/.test(cedula)) return;
      botonCrear.disabled = true;
      try {
        const respuesta = await fetch(
          formularioCandidato.dataset.candidateLookupUrl + "?cedula=" + encodeURIComponent(cedula),
          {headers: {"Accept": "application/json"}, credentials: "same-origin"}
        );
        if (numeroConsulta !== consultaActual) return;
        if (!respuesta.ok) {
          botonCrear.disabled = false;
          return;
        }
        const datos = await respuesta.json();
        if (numeroConsulta !== consultaActual) return;
        if (!datos.encontrado) {
          botonCrear.disabled = false;
          return;
        }
        const persona = datos.nombre + " " + datos.apellidos;
        const ultimo = datos.ultimo_proceso;
        const rechazoAnterior = datos.ultimo_rechazo;
        aviso.classList.add("alert-danger");
        if (rechazoAnterior) {
          resumen.textContent = persona + " ya estuvo en un proceso y fue rechazada. No se puede crear otro proceso con esta cédula.";
          contextoRechazo.textContent = "Vacante: " + rechazoAnterior.vacante + " · Se quedó en: " + rechazoAnterior.etapa + ".";
          motivoRechazo.textContent = rechazoAnterior.motivo;
          rechazo.classList.remove("d-none");
        } else if (datos.proceso_abierto) {
          resumen.textContent = persona + " ya tiene un proceso activo. No se puede crear otro proceso con esta cédula.";
        } else {
          resumen.textContent = persona + " ya tiene un proceso registrado" +
            (ultimo ? " para " + ultimo.vacante + " (" + ultimo.estado + ")" : "") +
            ". No se puede crear otro proceso con esta cédula.";
        }
        aviso.classList.remove("d-none");
      } catch (error) {
        if (numeroConsulta === consultaActual) botonCrear.disabled = false;
        // La validación del servidor seguirá protegiendo el registro si falla la consulta visual.
      }
    }

    campoCedula.addEventListener("input", function () {
      ++consultaActual;
      window.clearTimeout(temporizadorConsulta);
      limpiarAviso();
      const cedula = (campoCedula.value || "").replace(/[.\s-]/g, "");
      if (/^\d{5,15}$/.test(cedula)) {
        botonCrear.disabled = true;
        temporizadorConsulta = window.setTimeout(consultarCedula, 350);
      }
    });
    campoCedula.addEventListener("blur", function () {
      window.clearTimeout(temporizadorConsulta);
      consultarCedula();
    });
  }

  const resumenError = document.querySelector("[data-error-summary]");
  if (resumenError) resumenError.focus();
})();
