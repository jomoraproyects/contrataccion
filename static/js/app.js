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
    let consultaActual = 0;

    async function consultarCedula() {
      const cedula = (campoCedula.value || "").replace(/[.\s-]/g, "");
      const numeroConsulta = ++consultaActual;
      aviso.classList.add("d-none");
      aviso.textContent = "";
      aviso.classList.remove("alert-danger", "alert-info");
      if (!/^\d{5,15}$/.test(cedula)) return;
      try {
        const respuesta = await fetch(
          formularioCandidato.dataset.candidateLookupUrl + "?cedula=" + encodeURIComponent(cedula),
          {headers: {"Accept": "application/json"}, credentials: "same-origin"}
        );
        if (!respuesta.ok || numeroConsulta !== consultaActual) return;
        const datos = await respuesta.json();
        if (!datos.encontrado) return;
        document.getElementById("id_nombre").value = datos.nombre;
        document.getElementById("id_apellidos").value = datos.apellidos;
        document.getElementById("id_celular").value = datos.celular;
        const ultimo = datos.ultimo_proceso;
        if (datos.proceso_abierto) {
          aviso.classList.add("alert-danger");
          aviso.textContent = "Esta persona ya está registrada y tiene un proceso activo. Debe finalizarlo o desactivarlo antes de crear otro.";
        } else {
          aviso.classList.add("alert-info");
          aviso.textContent = "Persona ya registrada. Se recuperaron sus datos. Tiene " + datos.cantidad_procesos +
            " proceso(s) anterior(es)" + (ultimo ? ". Último: " + ultimo.vacante + " · " + ultimo.estado + " · " + ultimo.fecha + "." : ".");
        }
        aviso.classList.remove("d-none");
      } catch (error) {
        // La validación del servidor seguirá protegiendo el registro si falla la consulta visual.
      }
    }

    campoCedula.addEventListener("change", consultarCedula);
    campoCedula.addEventListener("blur", consultarCedula);
  }

  const resumenError = document.querySelector("[data-error-summary]");
  if (resumenError) resumenError.focus();
})();
