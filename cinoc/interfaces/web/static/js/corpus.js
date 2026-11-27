/* Bibliothèque — états d'interface, upload ZIP, imports distants et suppression.
 *
 * La page reste rendue serveur : ce script ne fait que piloter des onglets et
 * appeler les endpoints existants. Après succès, on recharge la page pour que
 * le HTML serveur reste la source de vérité.
 */
(function () {
  "use strict";

  var CSRF = "X-Cinoc-CSRF";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function fetchJson(url, opts) {
    return fetch(url, opts).then(function (res) {
      return res.json().then(
        function (body) {
          return { ok: res.ok, status: res.status, body: body };
        },
        function () {
          return { ok: res.ok, status: res.status, body: {} };
        }
      );
    });
  }

  function errorText(response) {
    var detail = response && response.body && response.body.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    return "HTTP " + response.status;
  }

  function collectField(payload, el) {
    if (!el || !el.name) return;
    if (el.type === "checkbox") {
      payload[el.name] = el.checked;
      return;
    }
    var value = (el.value || "").trim();
    if (value === "") return;
    payload[el.name] = el.type === "number" ? parseInt(value, 10) : value;
  }

  ready(function () {
    bindLibraryTabs();
    bindSourceTabs();
    bindUpload();
    bindImports();
    bindDelete();
  });

  function bindLibraryTabs() {
    var buttons = document.querySelectorAll("[data-library-tab]");
    var panels = document.querySelectorAll("[data-library-panel]");
    if (!buttons.length || !panels.length) return;

    function activate(tab) {
      for (var i = 0; i < buttons.length; i++) {
        var isActive = buttons[i].getAttribute("data-library-tab") === tab;
        buttons[i].classList.toggle("on", isActive);
        buttons[i].setAttribute("aria-selected", isActive ? "true" : "false");
      }
      for (var j = 0; j < panels.length; j++) {
        panels[j].hidden = panels[j].getAttribute("data-library-panel") !== tab;
      }
      if (window.location.hash !== "#" + tab) {
        history.replaceState(null, "", window.location.pathname + window.location.search + "#" + tab);
      }
    }

    for (var k = 0; k < buttons.length; k++) {
      buttons[k].addEventListener("click", function (event) {
        if (this.tagName === "A") {
          event.preventDefault();
        }
        activate(this.getAttribute("data-library-tab"));
      });
    }

    activate(window.location.hash.indexOf("#discover") === 0 ? "discover" : "corpora");
  }

  function bindSourceTabs() {
    var chips = document.querySelectorAll("[data-source-tab]");
    var panels = document.querySelectorAll("[data-source-panel]");
    if (!chips.length || !panels.length) return;

    // ``pushHash`` = false à l'initialisation : on prépare seulement le panneau
    // source visible, SANS réécrire le hash global. Sinon l'activation au
    // chargement forçait ``#discover:…`` même sur l'onglet « Mes corpus », et un
    // reload (ex. après upload) atterrissait à tort sur « Découverte ».
    function activate(source, pushHash) {
      for (var i = 0; i < chips.length; i++) {
        var isActive = chips[i].getAttribute("data-source-tab") === source;
        chips[i].classList.toggle("on", isActive);
        chips[i].setAttribute("aria-selected", isActive ? "true" : "false");
      }
      for (var j = 0; j < panels.length; j++) {
        panels[j].hidden = panels[j].getAttribute("data-source-panel") !== source;
      }
      if (!pushHash) return;
      var url = new URL(window.location.href);
      url.hash = "discover:" + source;
      history.replaceState(null, "", url.toString());
      if (window.location.hash.indexOf("#discover") !== 0) {
        var discoverBtn = document.querySelector('[data-library-tab="discover"]');
        if (discoverBtn) discoverBtn.click();
      }
    }

    for (var k = 0; k < chips.length; k++) {
      chips[k].addEventListener("click", function (event) {
        if (this.tagName === "A") {
          event.preventDefault();
        }
        activate(this.getAttribute("data-source-tab"), true);
      });
    }

    var hash = window.location.hash || "";
    var initial = hash.indexOf("#discover:") === 0 ? hash.slice(10) : "htr-united";
    activate(initial, false);
  }

  function bindUpload() {
    var fileEl = document.getElementById("corpus-file");
    var statusEl = document.getElementById("corpus-status");
    var dropzone = document.getElementById("dropzone");

    function upload(file) {
      if (!file) return;
      var headers = {};
      headers[CSRF] = "1";
      var form = new FormData();
      form.append("file", file);
      if (statusEl) statusEl.textContent = "…";
      fetchJson("/api/corpus", { method: "POST", headers: headers, body: form })
        .then(function (response) {
          if (!response.ok) {
            // Refus pour taille : le message de la page, dans sa langue, qui
            // nomme le plafond que le serveur applique (D-310).
            var localized =
              statusEl && statusEl.getAttribute("data-error-" + response.status);
            if (statusEl) statusEl.textContent = localized || errorText(response);
            return;
          }
          window.location.reload();
        })
        .catch(function () {
          if (statusEl) statusEl.textContent = "HTTP 0";
        });
    }

    if (fileEl) {
      fileEl.addEventListener("change", function () {
        upload(fileEl.files && fileEl.files[0]);
      });
    }

    if (!dropzone) return;
    ["dragenter", "dragover"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropzone.classList.remove("is-dragover");
      });
    });
    dropzone.addEventListener("drop", function (e) {
      var dataTransfer = e.dataTransfer;
      var file = dataTransfer && dataTransfer.files && dataTransfer.files[0];
      if (file) upload(file);
    });
  }

  function bindImports() {
    var buttons = document.querySelectorAll("[data-import-source]");
    if (!buttons.length) return;

    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function () {
        var source = this.getAttribute("data-import-source");
        if (!source) return;
        runImport(this, source);
      });
    }
  }

  function runImport(button, source) {
    var statusEl = document.querySelector('[data-import-status="' + source + '"]');
    var group = document.querySelector('.import-fields[data-source="' + source + '"]');
    var payload = {};
    var fields = group ? group.querySelectorAll("input[name]") : [];
    for (var i = 0; i < fields.length; i++) collectField(payload, fields[i]);
    var shared = document.querySelectorAll(
      '[data-source-panel="' + source + '"] [data-import-shared]'
    );
    for (var j = 0; j < shared.length; j++) collectField(payload, shared[j]);

    var datasetId = button.getAttribute("data-dataset-id");
    if (datasetId) payload.dataset_id = datasetId;

    // Carte « Cinoc curé » découverte : l'identifiant (et la révision pinnée, si
    // l'API la fournit) viennent du bouton — ils priment sur le formulaire manuel.
    var repoId = button.getAttribute("data-repo-id");
    if (repoId) {
      payload.repo_id = repoId;
      var revision = button.getAttribute("data-revision");
      if (revision) payload.revision = revision;
    }

    var headers = { "Content-Type": "application/json" };
    headers[CSRF] = "1";
    button.disabled = true;
    if (statusEl) statusEl.textContent = "…";
    fetchJson("/api/corpus/import/" + source, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        button.disabled = false;
        if (!response.ok) {
          if (statusEl) statusEl.textContent = errorText(response);
          return;
        }
        window.location.reload();
      })
      .catch(function () {
        button.disabled = false;
        if (statusEl) statusEl.textContent = "HTTP 0";
      });
  }

  function bindDelete() {
    var buttons = document.querySelectorAll(".c-del[data-corpus]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function () {
        var id = this.getAttribute("data-corpus");
        if (!id) return;
        var headers = {};
        headers[CSRF] = "1";
        this.disabled = true;
        fetchJson("/api/corpus/" + encodeURIComponent(id), {
          method: "DELETE",
          headers: headers,
        })
          .then(function (response) {
            if (response.ok) window.location.reload();
          })
          .catch(function () {});
      });
    }
  }
})();
