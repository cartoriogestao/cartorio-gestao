/* Navegação progressiva do shell do sistema.
   Os links e os <details> funcionam sem JavaScript; este arquivo apenas torna
   uma lista grande mais rápida de percorrer e adapta o menu a telas pequenas. */
(function () {
  "use strict";

  var sidebar = document.getElementById("app-sidebar");
  if (!sidebar) return;

  var root = document.documentElement;
  var body = document.body;
  var toggle = document.querySelector(".sidebar-toggle");
  var scrim = document.querySelector(".sidebar-scrim");
  var collapseBtn = document.querySelector(".sidebar-collapse");
  var desktopNav = window.matchMedia("(min-width: 901px)");
  var STORAGE_COLLAPSE = "cg-sidebar-recolhida";
  var search = document.getElementById("nav-search");
  var status = document.getElementById("nav-search-status");
  var modules = Array.prototype.slice.call(sidebar.querySelectorAll(".nav-modulo"));
  var sectionLabels = Array.prototype.slice.call(sidebar.querySelectorAll(".nav-grupo"));

  /* Marca o destino exato sem obrigar cada uma das muitas rotas a repetir
     lógica no template. O módulo aberto continua sendo decidido no servidor. */
  Array.prototype.slice.call(sidebar.querySelectorAll("nav a[href]")).forEach(function (link) {
    var target = new URL(link.href, window.location.href);
    if (target.pathname === window.location.pathname && target.search === window.location.search) {
      link.classList.add("atual");
      link.setAttribute("aria-current", "page");
    }
  });

  function setMenu(open) {
    body.classList.toggle("nav-aberta", open);
    if (toggle) {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
    }
  }

  if (toggle) toggle.addEventListener("click", function () {
    setMenu(!body.classList.contains("nav-aberta"));
  });
  if (scrim) scrim.addEventListener("click", function () { setMenu(false); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setMenu(false);
  });

  function sidebarRecolhida() {
    return root.classList.contains("sidebar-recolhida");
  }

  function setSidebarRecolhida(recolhida, persist) {
    if (!desktopNav.matches) {
      root.classList.remove("sidebar-recolhida");
      return;
    }
    root.classList.toggle("sidebar-recolhida", recolhida);
    if (collapseBtn) {
      var expandir = recolhida;
      var tooltip = expandir ? "Expandir menu" : "Recolher menu";
      collapseBtn.setAttribute("aria-expanded", expandir ? "false" : "true");
      collapseBtn.setAttribute("aria-label", tooltip);
      collapseBtn.setAttribute("title", tooltip);
      var label = collapseBtn.querySelector(".sidebar-collapse-text");
      if (label) label.textContent = tooltip;
    }
    if (persist !== false) {
      try {
        localStorage.setItem(STORAGE_COLLAPSE, recolhida ? "1" : "0");
      } catch (e) { /* ignorar */ }
    }
  }

  if (collapseBtn) {
    collapseBtn.addEventListener("click", function () {
      setSidebarRecolhida(!sidebarRecolhida());
    });
  }

  function syncCollapseFromStorage() {
    if (!desktopNav.matches) {
      root.classList.remove("sidebar-recolhida");
      return;
    }
    var stored = false;
    try {
      stored = localStorage.getItem(STORAGE_COLLAPSE) === "1";
    } catch (e) { /* ignorar */ }
    setSidebarRecolhida(stored, false);
  }

  syncCollapseFromStorage();
  if (typeof desktopNav.addEventListener === "function") {
    desktopNav.addEventListener("change", syncCollapseFromStorage);
  } else if (typeof desktopNav.addListener === "function") {
    desktopNav.addListener(syncCollapseFromStorage);
  }
  sidebar.addEventListener("click", function (event) {
    if (desktopNav.matches && sidebarRecolhida()
        && event.target.closest("a, .nav-modulo > summary")) {
      setSidebarRecolhida(false);
    }
    if (event.target.closest("a") && window.matchMedia("(max-width: 900px)").matches) {
      setMenu(false);
    }
  });

  modules.forEach(function (module) {
    module.addEventListener("toggle", function () {
      if (!module.open || (search && search.value.trim())) return;
      modules.forEach(function (other) {
        if (other !== module) other.open = false;
      });
    });
  });

  if (!search) return;
  var originalOpen = modules.map(function (module) { return module.open; });
  var plain = function (value) {
    return (value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  };

  function updateGroupLabels() {
    sectionLabels.forEach(function (label) {
      var next = label.nextElementSibling;
      var visible = false;
      while (next && !next.classList.contains("nav-grupo")) {
        if (!next.hidden) visible = true;
        next = next.nextElementSibling;
      }
      label.hidden = !visible;
    });
  }

  function filterNavigation() {
    var query = plain(search.value.trim());
    var found = 0;

    modules.forEach(function (module, moduleIndex) {
      var summary = module.querySelector("summary");
      var links = Array.prototype.slice.call(module.querySelectorAll(":scope > a"));
      var moduleMatch = query && plain(summary.textContent).indexOf(query) !== -1;

      links.forEach(function (link) {
        var match = !query || moduleMatch || plain(link.textContent).indexOf(query) !== -1;
        link.hidden = !match;
        if (query && match) found += 1;
      });

      Array.prototype.slice.call(module.querySelectorAll(":scope > .nav-secao")).forEach(function (section) {
        var next = section.nextElementSibling;
        var hasVisibleLink = false;
        while (next && !next.classList.contains("nav-secao")) {
          if (next.tagName === "A" && !next.hidden) hasVisibleLink = true;
          next = next.nextElementSibling;
        }
        section.hidden = Boolean(query) && !hasVisibleLink;
      });

      var anyVisible = links.some(function (link) { return !link.hidden; });
      module.hidden = Boolean(query) && !moduleMatch && !anyVisible;
      module.open = query ? !module.hidden : originalOpen[moduleIndex];
    });

    var home = sidebar.querySelector(".nav-inicio");
    if (home) {
      var homeMatch = !query || plain(home.textContent).indexOf(query) !== -1;
      home.hidden = !homeMatch;
      if (query && homeMatch) found += 1;
    }

    updateGroupLabels();
    status.textContent = query ? (found ? found + " resultado(s)" : "Nenhum resultado") : "";
  }

  search.addEventListener("input", filterNavigation);
  search.addEventListener("search", filterNavigation);
})();
