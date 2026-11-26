/* Banc d'essai — la file, le lancement et le suivi SSE.
 *
 * recipes.js compose les entrées (une recette, ses briques, ses réglages) et
 * les pose dans la file ; ce script la montre, l'exporte, la réimporte et la
 * lance par POST /api/runs — un seul chemin pour toute forme de run (D-298).
 * Le serveur reste la source de vérité pour le lancement et les erreurs ; le
 * client ne traduit que les états HTTP en messages lisibles.
 */
(function () {
  "use strict";

  var CSRF = "X-Cinoc-CSRF";
  var STATES = ["pending", "running", "done", "failed", "cancelled"];
  var TERMINAL = { done: 1, failed: 1, cancelled: 1 };

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

  function wireNormalizationPreview() {
    var btn = document.getElementById("norm-preview-btn");
    var sample = document.getElementById("norm-sample");
    var config = document.getElementById("norm-config");
    var select = document.getElementById("normalization");
    var out = document.getElementById("norm-result");
    if (!btn || !sample || !out) return;
    btn.addEventListener("click", function () {
      var payload = { sample: sample.value };
      var custom = config && config.value ? config.value.trim() : "";
      if (custom) payload.config = custom;
      else if (select && select.value) payload.profile = select.value;
      var headers = { "Content-Type": "application/json" };
      headers[CSRF] = "1";
      out.textContent = "…";
      fetchJson("/api/normalization/preview", {
        method: "POST",
        headers: headers,
        body: JSON.stringify(payload),
      }).then(function (r) {
        out.textContent = r.ok
          ? r.body.normalized || ""
          : "Erreur : " + (r.body.detail || r.status);
      });
    });
  }

  // Aperçu de mise en page (recette qui segmente) : lance une segmentation sur
  // le corpus choisi, avec le segmenteur et l'adresse de l'étape, et injecte le
  // SVG des régions (rendu serveur). Un transport, gardé tel quel (D-298).
  function wireSegPreview() {
    var btn = document.getElementById("seg-preview-btn");
    var container = document.getElementById("seg-preview");
    if (!btn || !container) return;
    var status = document.getElementById("seg-preview-status");
    var corpusSelect = document.getElementById("corpus-select");

    function stepField(step, name) {
      var field = document.querySelector(
        '#recipe-steps [data-step="' + step + '"][data-param="' + name + '"]'
      );
      return field && field.value.trim();
    }

    function poll(jobId) {
      fetchJson("/api/runs/" + encodeURIComponent(jobId)).then(function (res) {
        var state = res.body && res.body.state;
        if (state === "done") {
          // Le sink clé le store par id propre → on lit le dernier layout persisté.
          fetch("/api/segmentation/preview")
            .then(function (r) {
              return r.ok ? r.text() : "";
            })
            .then(function (svg) {
              container.innerHTML = svg;
              if (status) status.textContent = "";
              btn.disabled = false;
            });
          return;
        }
        if (state === "failed" || state === "cancelled" || !res.ok) {
          if (status) {
            status.textContent =
              (res.body && res.body.error) || "HTTP " + res.status;
          }
          btn.disabled = false;
          return;
        }
        window.setTimeout(function () {
          poll(jobId);
        }, 1500);
      });
    }

    btn.addEventListener("click", function () {
      var corpusId = corpusSelect && corpusSelect.value;
      if (!corpusId) {
        if (status) status.textContent = btn.getAttribute("data-no-corpus") || "";
        return;
      }
      var segmenter = document.querySelector('#recipe-steps select[data-role="segmenter"]');
      var step = segmenter && segmenter.getAttribute("data-step");
      var payload = { corpus_id: corpusId, segmenter: segmenter ? segmenter.value : "" };
      if (stepField(step, "endpoint")) payload.endpoint = stepField(step, "endpoint");
      if (stepField(step, "token")) payload.token = stepField(step, "token");
      var headers = { "Content-Type": "application/json" };
      headers[CSRF] = "1";
      btn.disabled = true;
      if (status) status.textContent = status.getAttribute("data-running") || "…";
      fetchJson("/api/segmentation/run", {
        method: "POST",
        headers: headers,
        body: JSON.stringify(payload),
      }).then(function (res) {
        if (!res.ok) {
          if (status) {
            status.textContent =
              (res.body && res.body.detail) || "HTTP " + res.status;
          }
          btn.disabled = false;
          return;
        }
        poll(res.body.job_id);
      });
    });
  }

  ready(function () {
    wireNormalizationPreview();
    wireSegPreview();
    var launchBtn = document.getElementById("launch");
    var statusEl = document.getElementById("run-status");
    var resultEl = document.getElementById("run-result");
    var logEl = document.getElementById("run-log");
    var logShell = document.getElementById("run-log-shell");
    var progressWrap = document.getElementById("run-progress");
    var progressBar = document.getElementById("run-progress-bar");
    var progressText = document.getElementById("run-progress-text");
    var corpusSelect = document.getElementById("corpus-select");
    var normalization = document.getElementById("normalization");
    var charExclude = document.getElementById("char-exclude");
    var metricProfile = document.getElementById("metric-profile");
    var queueTpl = document.getElementById("queue-row-tpl");
    var queueList = document.getElementById("queue-list");
    var queueEmpty = document.getElementById("queue-empty");
    if (!launchBtn || !statusEl || !resultEl || !queueList || !queueTpl) return;

    // La file : des entrées de ``entries`` (une recette, ses choix, ses réglages,
    // ses étapes facultatives), décrites par recipes.js.
    var queue = [];

    function currentCorpusId() {
      return corpusSelect && corpusSelect.value ? corpusSelect.value : null;
    }

    function applyQueryCorpus() {
      var corpusId = new URLSearchParams(window.location.search).get("corpus");
      if (corpusId && corpusSelect) corpusSelect.value = corpusId;
    }

    function summarize(request) {
      var recipes = window.cinocRecipes;
      return recipes ? recipes.describe(request) : { label: request.recipe, meta: "" };
    }

    function renderQueue() {
      queueList.textContent = "";
      if (queueEmpty) queueEmpty.hidden = queue.length > 0;
      for (var i = 0; i < queue.length; i++) {
        var node = queueTpl.content.firstElementChild.cloneNode(true);
        var summary = summarize(queue[i]);
        node.querySelector(".queue-id").textContent = "C0" + (i + 1);
        node.querySelector(".queue-label").textContent = summary.label;
        node.querySelector(".queue-meta").textContent = summary.meta;
        bindRemove(node.querySelector(".queue-remove"), i);
        queueList.appendChild(node);
      }
    }

    function bindRemove(button, index) {
      if (!button) return;
      button.addEventListener("click", function () {
        queue.splice(index, 1);
        renderQueue();
      });
    }

    // Config save/load — l'« état du formulaire » EST un LaunchRequest (même
    // schéma que le POST /api/runs) : la file entière et les options. Export =
    // blob JSON téléchargé (0 réseau) ; import = validé côté serveur (POST
    // /api/runs/config) AVANT de repeupler — un fichier malformé est rejeté net.
    function withScoring(cfg) {
      var corpusId = currentCorpusId();
      if (corpusId) cfg.corpus_id = corpusId;
      if (normalization && normalization.value) cfg.normalization = normalization.value;
      if (charExclude && charExclude.value) cfg.char_exclude = charExclude.value;
      if (metricProfile && metricProfile.value) cfg.metric_profile = metricProfile.value;
      return cfg;
    }

    function collectConfig() {
      return withScoring({ entries: queue.slice() });
    }

    function exportConfig() {
      var text = JSON.stringify(collectConfig(), null, 2);
      var uri = "data:application/json;charset=utf-8," + encodeURIComponent(text);
      var a = document.createElement("a");
      a.href = uri;
      a.download = "cinoc-config.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }

    function applyConfig(cfg) {
      queue = (cfg.entries || []).slice();
      renderQueue();
      if (corpusSelect) corpusSelect.value = cfg.corpus_id || "";
      if (normalization) normalization.value = cfg.normalization || "";
      if (charExclude) charExclude.value = cfg.char_exclude || "";
      if (metricProfile && cfg.metric_profile) metricProfile.value = cfg.metric_profile;
    }

    function importConfig(file, feedback) {
      var reader = new FileReader();
      reader.onload = function () {
        var parsed;
        try {
          parsed = JSON.parse(reader.result);
        } catch (e) {
          feedback.textContent = feedback.dataset.invalid || "invalid";
          return;
        }
        var headers = { "Content-Type": "application/json" };
        headers[CSRF] = "1";
        fetchJson("/api/runs/config", {
          method: "POST",
          headers: headers,
          body: JSON.stringify(parsed),
        }).then(function (r) {
          if (!r.ok) {
            feedback.textContent = feedback.dataset.invalid || "invalid";
            return;
          }
          applyConfig(r.body.config || {});
          feedback.textContent = feedback.dataset.loaded || "loaded";
        });
      };
      reader.readAsText(file);
    }

    function errorText(response) {
      var detail = response && response.body && response.body.detail;
      if (typeof detail === "string" && detail.trim()) return detail;
      var specific = resultEl.getAttribute("data-error-" + response.status);
      return specific || resultEl.dataset.errorFallback || ("HTTP " + response.status);
    }

    function resetRunFeedback(launchingText) {
      statusEl.textContent = launchingText || "…";
      resultEl.textContent = "";
      if (logEl) logEl.textContent = "";
      if (logShell) {
        logShell.hidden = false;
        logShell.open = true;
      }
    }

    function appendLog(state, job) {
      if (!logEl) return;
      var line = document.createElement("div");
      line.textContent = (job.updated_at || "—") + "  ·  " + state;
      logEl.appendChild(line);
    }

    function updateProgress(job) {
      if (!progressWrap || !progressBar) return;
      var total = job.total || 0;
      var doneN = job.done || 0;
      if (total <= 0) return;
      progressWrap.hidden = false;
      var pct = Math.round((doneN / total) * 100);
      progressBar.style.width = pct + "%";
      var rail = document.getElementById("run-progress-rail");
      if (rail) rail.setAttribute("aria-valuenow", String(pct));
      if (progressText) progressText.textContent = doneN + " / " + total;
    }

    function resetProgress() {
      if (progressBar) progressBar.style.width = "0%";
      if (progressText) progressText.textContent = "";
      if (progressWrap) progressWrap.hidden = true;
    }

    function subscribe(jobId, onTerminal) {
      var es = new EventSource("/api/runs/" + encodeURIComponent(jobId) + "/events");
      var finished = false;

      function done(state, job) {
        if (finished) return;
        finished = true;
        es.close();
        onTerminal(state, job || {});
      }

      STATES.forEach(function (state) {
        es.addEventListener(state, function (ev) {
          var job = JSON.parse(ev.data);
          statusEl.textContent = state;
          appendLog(state, job);
          updateProgress(job);
          if (TERMINAL[state]) done(state, job);
        });
      });

      es.onerror = function () {
        if (es.readyState === EventSource.CLOSED) done("failed", {});
      };
    }

    // Lancer un run et le suivre : poster, gérer l'erreur, suivre en SSE,
    // rendre la main.
    function launchAndFollow(url, payload, button) {
      button.disabled = true;
      resetRunFeedback(button.dataset.launching);
      resetProgress();
      var headers = { "Content-Type": "application/json" };
      headers[CSRF] = "1";
      fetchJson(url, {
        method: "POST",
        headers: headers,
        body: JSON.stringify(payload),
      })
        .then(function (response) {
          if (!response.ok) {
            statusEl.textContent = "HTTP " + response.status;
            resultEl.textContent = errorText(response);
            button.disabled = false;
            return;
          }
          subscribe(response.body.job_id, function (state, job) {
            button.disabled = false;
            reportTerminal(state, job);
          });
        })
        .catch(function () {
          statusEl.textContent = resultEl.dataset.neterror || "HTTP 0";
          resultEl.textContent = resultEl.dataset.errorFallback || "HTTP 0";
          button.disabled = false;
        });
    }

    function reportTerminal(state, job) {
      if (state === "done" && job.report_name) {
        var link = document.createElement("a");
        link.href = "/reports/" + encodeURIComponent(job.report_name);
        link.className = "btn btn-primary";
        link.textContent = resultEl.dataset.open || "report";
        resultEl.appendChild(link);
        return;
      }
      resultEl.textContent = job.error || (resultEl.dataset.errorFallback || "failed");
    }

    renderQueue();
    // recipes.js y pose les entrées composées.
    window.cinocQueue = { add: function (e) { queue.push(e); renderQueue(); } };

    applyQueryCorpus();

    var exportBtn = document.getElementById("config-export");
    var importInput = document.getElementById("config-import");
    var configFeedback = document.getElementById("config-feedback");
    if (exportBtn) exportBtn.addEventListener("click", exportConfig);
    if (importInput && configFeedback) {
      importInput.addEventListener("change", function () {
        if (importInput.files && importInput.files[0]) {
          importConfig(importInput.files[0], configFeedback);
        }
      });
    }

    // Une file de recettes, quelles qu'elles soient, part en un seul run ;
    // vide et sans corpus, c'est la démonstration.
    launchBtn.addEventListener("click", function () {
      if (queue.length && !currentCorpusId()) {
        resultEl.textContent = queueList.dataset.noCorpus || "";
        return;
      }
      launchAndFollow("/api/runs", collectConfig(), launchBtn);
    });
  });
})();
