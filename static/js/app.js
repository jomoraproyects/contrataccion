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

  document.querySelectorAll("form[data-stage-checklist]").forEach((formulario) => {
    const filas = Array.from(formulario.querySelectorAll("[data-checklist-row]"));
    const aprobar = formulario.querySelector('input[name="resultado"][value="APROBADO"]');
    const rechazar = formulario.querySelector('input[name="resultado"][value="RECHAZADO"]');
    const observacion = formulario.querySelector('textarea[name="observacion"]');
    const boton = formulario.querySelector('button[type="submit"]');
    const etiqueta = boton.querySelector("[data-submit-label]");
    const estado = formulario.querySelector("[data-checklist-status]");

    function actualizarVerificacion() {
      const seleccionados = filas.map((fila) => fila.querySelector('input[type="radio"]:checked'));
      const revisados = seleccionados.filter(Boolean).length;
      const fallos = seleccionados.filter((input) => input && input.value === "NO_CUMPLE").length;
      const completa = revisados === filas.length;
      aprobar.disabled = !completa || fallos > 0;
      rechazar.disabled = !completa || fallos === 0;
      aprobar.checked = completa && fallos === 0;
      rechazar.checked = completa && fallos > 0;
      const notaCompleta = observacion.value.trim().length >= 3;
      boton.disabled = !completa || !notaCompleta;
      formulario.querySelector("[data-checklist-count]").textContent = revisados + " de " + filas.length + " revisados";
      filas.forEach((fila, index) => {
        fila.classList.toggle("is-complete", !!seleccionados[index] && seleccionados[index].value === "CUMPLE");
        fila.classList.toggle("is-failed", !!seleccionados[index] && seleccionados[index].value === "NO_CUMPLE");
      });
      const mensaje = !completa
        ? "Falta revisar " + (filas.length - revisados) + " requisito(s). Un requisito pendiente no genera un rechazo automático."
        : fallos
          ? "Hay " + fallos + " requisito(s) que no cumple. Escriba la observación para registrar el rechazo."
          : "Todos los requisitos cumplen. Escriba la observación para aprobar y continuar.";
      if (estado.textContent !== mensaje) estado.textContent = mensaje;
      estado.classList.toggle("is-failed", completa && fallos > 0);
      estado.classList.toggle("is-complete", completa && fallos === 0);
      etiqueta.textContent = !completa ? "Complete la verificación" : fallos ? "Rechazar y finalizar" : "Aprobar y continuar";
    }

    formulario.addEventListener("change", actualizarVerificacion);
    observacion.addEventListener("input", actualizarVerificacion);
    formulario.addEventListener("submit", function (evento) {
      actualizarVerificacion();
      if (boton.disabled) {
        evento.preventDefault();
        evento.stopImmediatePropagation();
        const pendiente = filas.find((fila) => !fila.querySelector('input[type="radio"]:checked'));
        if (pendiente) pendiente.querySelector("input").focus();
        else observacion.focus();
      }
    });
    actualizarVerificacion();
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
    const requisitosRechazo = aviso.querySelector("[data-candidate-rejection-requirements]");
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
      requisitosRechazo.textContent = "";
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
          requisitosRechazo.textContent = rechazoAnterior.requisitos && rechazoAnterior.requisitos.length
            ? "No cumplió: " + rechazoAnterior.requisitos.join(", ") + "."
            : "";
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
