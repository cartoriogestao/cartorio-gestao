(function () {
  "use strict";

  var STORAGE_KEY = "nu_avisos_overlay_fechado";
  var overlay = document.querySelector("[data-nu-avisos-overlay]");
  if (!overlay) return;
  var modal = overlay.querySelector("[data-nu-avisos-modal]");
  if (!modal) return;
  var formFechar = overlay.querySelector("[data-nu-avisos-fechar]");
  var faixas = document.querySelector("[data-main-compact-banners]");

  function exibirFaixasCompactas() {
    if (!faixas) return;
    faixas.hidden = false;
    faixas.removeAttribute("hidden");
  }

  function persistirOverlayFechado() {
    if (!formFechar) return Promise.resolve(false);
    var fd = new FormData(formFechar);
    return fetch(formFechar.action, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (resp) {
        return resp.ok || resp.redirected;
      })
      .catch(function () {
        return false;
      });
  }

  function fecharModal(opcoes) {
    opcoes = opcoes || {};
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    overlay.style.display = "none";
    document.removeEventListener("keydown", trapFocus);
    try {
      sessionStorage.setItem(STORAGE_KEY, "1");
    } catch (_e) {
      /* ignore */
    }
    exibirFaixasCompactas();
    if (opcoes.skipPersist) {
      return Promise.resolve(true);
    }
    return persistirOverlayFechado();
  }

  if (formFechar) {
    formFechar.addEventListener("submit", function () {
      fecharModal({ skipPersist: true });
    });
  }

  overlay.addEventListener(
    "click",
    function (event) {
      var link = event.target.closest("a[href]");
      if (!link || !overlay.contains(link)) return;
      var href = link.getAttribute("href");
      if (!href || href.charAt(0) === "#") return;
      event.preventDefault();
      fecharModal().then(function () {
        window.location.assign(link.href);
      });
    },
    true
  );

  function prenderFoco(el) {
    return el && el.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
  }

  function trapFocus(event) {
    if (event.key === "Escape") {
      var fechar = overlay.querySelector("[data-nu-avisos-fechar]");
      if (fechar) {
        event.preventDefault();
        fechar.requestSubmit();
      }
      return;
    }
    if (event.key !== "Tab" || !modal) return;
    var focaveis = prenderFoco(modal);
    if (!focaveis.length) return;
    var primeiro = focaveis[0];
    var ultimo = focaveis[focaveis.length - 1];
    if (event.shiftKey && document.activeElement === primeiro) {
      event.preventDefault();
      ultimo.focus();
    } else if (!event.shiftKey && document.activeElement === ultimo) {
      event.preventDefault();
      primeiro.focus();
    }
  }

  document.addEventListener("keydown", trapFocus);
  modal.focus();
})();
