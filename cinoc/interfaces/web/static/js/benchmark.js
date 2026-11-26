/* Banc d'essai — la file, le lancement et le suivi SSE.
 *
 * recipes.js compose les entrées (une recette, ses briques, ses réglages) et
 * les pose dans la file ; ce script la montre, l'exporte, la réimporte et la
 * lance par POST /api/runs — un seul chemin pour toute forme de run (D-298).
 * Un run lancé s'arrête par « Arrêter » (POST /api/runs/{id}/cancel :
 * annulation coopérative, RunControl). Un secret ne sort jamais d'un export :
 * la forme exportée est celle du serveur, qui le retire et le nomme
 * (withheld_secrets) ; l'import le redemande dans la file (D-299). Une spec
 * complète déposée part par POST /api/runs/spec (instance privée).
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

  // Écriture : JSON + en-tête CSRF, la seule forme qu'accepte le serveur.
  function postJson(url, payload) {
    var headers = { "Content-Type": "application/json" };
    headers[CSRF] = "1";
    return fetchJson(url, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(payload || {}),
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
      out.textContent = "…";
      postJson("/api/normalization/preview", payload).then(function (r) {
        out.textContent = r.ok
          ? r.body.normalized || ""
          : "Erreur : " + (r.body.detail || r.status);
      });
    });
  }

  ready(function () {
    wireNormalizationPreview();
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
    var stopBtn = document.getElementById("run-stop");
    var configFeedback = document.getElementById("config-feedback");
    if (!launchBtn || !statusEl || !resultEl || !queueList || !queueTpl) return;

    // La file : des entrées de ``entries`` (une recette, ses choix, ses réglages,
    // ses étapes facultatives), décrites par recipes.js. ``slots`` garde, pour
    // chaque entrée, les secrets qu'un import a retirés — le champ reste
    // affiché (et corrigeable) une fois ressaisi.
    var queue = [];
    var slots = [];
    var currentJob = null;

    function stateText(state) {
      return statusEl.getAttribute("data-state-" + state) || state;
    }

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
        secretFields(node.querySelector(".queue-secrets"), i);
        queueList.appendChild(node);
      }
    }

    function bindRemove(button, index) {
      if (!button) return;
      button.addEventListener("click", function () {
        queue.splice(index, 1);
        slots.splice(index, 1);
        renderQueue();
      });
    }

    // Les secrets qu'un import a retirés : recipes.js rend leurs champs (il
    // rend tous les réglages), la file en garde la place.
    function secretFields(box, index) {
      var recipes = window.cinocRecipes;
      if (!box || !recipes) return;
      recipes.secretFields(box, queue[index], slots[index] || [],
        queueList.getAttribute("data-secret-label") || "");
    }

    function missingSecrets() {
      return queue.some(function (entry) {
        return (entry.withheld_secrets || []).length > 0;
      });
    }

    // Config save/load — l'« état du formulaire » EST un LaunchRequest (même
    // schéma que le POST /api/runs) : la file entière et les options. Export =
    // la forme canonique du serveur (POST /api/runs/config), **sans secret**,
    // téléchargée en blob ; import = validé par la même route AVANT de
    // repeupler — un fichier malformé est rejeté net.
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

    function postConfig(cfg) {
      return postJson("/api/runs/config", cfg);
    }

    function exportConfig() {
      postConfig(collectConfig()).then(function (r) {
        if (!r.ok) {
          if (configFeedback) {
            configFeedback.textContent = configFeedback.dataset.invalid || "invalid";
          }
          return;
        }
        var text = JSON.stringify(r.body.config || {}, null, 2);
        var uri = "data:application/json;charset=utf-8," + encodeURIComponent(text);
        var a = document.createElement("a");
        a.href = uri;
        a.download = "cinoc-config.json";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      });
    }

    function applyConfig(cfg) {
      queue = (cfg.entries || []).slice();
      slots = queue.map(function (entry) {
        return (entry.withheld_secrets || []).slice();
      });
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
        postConfig(parsed).then(function (r) {
          if (!r.ok) {
            feedback.textContent = feedback.dataset.invalid || "invalid";
            return;
          }
          applyConfig(r.body.config || {});
          feedback.textContent = (feedback.dataset.loaded || "loaded") +
            (missingSecrets() ? " " + (feedback.dataset.secrets || "") : "");
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
          statusEl.textContent = stateText(state);
          appendLog(state, job);
          updateProgress(job);
          if (TERMINAL[state]) done(state, job);
        });
      });

      es.onerror = function () {
        if (es.readyState === EventSource.CLOSED) done("failed", {});
      };
    }

    // « Arrêter » : visible le temps d'un run. Demande l'annulation
    // coopérative ; l'état « annulé » arrive par le flux SSE, comme les autres.
    function showStop(jobId) {
      currentJob = jobId;
      if (!stopBtn) return;
      stopBtn.textContent = stopBtn.dataset.label || stopBtn.textContent;
      stopBtn.disabled = false;
      stopBtn.hidden = false;
    }

    function hideStop() {
      currentJob = null;
      if (!stopBtn) return;
      var hadFocus = document.activeElement === stopBtn;
      stopBtn.hidden = true;
      if (hadFocus) launchBtn.focus();
    }

    if (stopBtn) {
      stopBtn.dataset.label = stopBtn.textContent;
      stopBtn.addEventListener("click", function () {
        if (!currentJob) return;
        stopBtn.disabled = true;
        stopBtn.textContent = stopBtn.dataset.stopping || "…";
        postJson("/api/runs/" + encodeURIComponent(currentJob) + "/cancel").then(function (r) {
          if (!r.ok || !r.body.cancelled) {
            stopBtn.textContent = stopBtn.dataset.late || stopBtn.dataset.label;
          }
        });
      });
    }

    // Lancer un run et le suivre : poster, gérer l'erreur, suivre en SSE,
    // rendre la main.
    function launchAndFollow(url, payload, button) {
      button.disabled = true;
      resetRunFeedback(button.dataset.launching);
      resetProgress();
      postJson(url, payload)
        .then(function (response) {
          if (!response.ok) {
            statusEl.textContent = "HTTP " + response.status;
            resultEl.textContent = errorText(response);
            button.disabled = false;
            return;
          }
          showStop(response.body.job_id);
          subscribe(response.body.job_id, function (state, job) {
            button.disabled = false;
            hideStop();
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
      if (state === "cancelled") {
        resultEl.textContent = resultEl.dataset.cancelled || "cancelled";
        return;
      }
      resultEl.textContent = job.error || (resultEl.dataset.errorFallback || "failed");
    }

    renderQueue();
    // recipes.js y pose les entrées composées.
    window.cinocQueue = {
      add: function (e) { queue.push(e); slots.push([]); renderQueue(); },
    };

    applyQueryCorpus();

    var exportBtn = document.getElementById("config-export");
    var importInput = document.getElementById("config-import");
    if (exportBtn) exportBtn.addEventListener("click", exportConfig);
    if (importInput && configFeedback) {
      importInput.addEventListener("change", function () {
        if (importInput.files && importInput.files[0]) {
          importConfig(importInput.files[0], configFeedback);
        }
      });
    }

    // La porte « spec complète » : un fichier déposé part tel quel, sur le
    // corpus choisi ; le serveur applique les gardes de la file (D-299).
    var specInput = document.getElementById("spec-file");
    if (specInput) {
      specInput.addEventListener("change", function () {
        var file = specInput.files && specInput.files[0];
        if (!file) return;
        if (!currentCorpusId()) {
          resultEl.textContent = queueList.dataset.noCorpus || "";
          return;
        }
        file.text().then(function (text) {
          specInput.value = "";
          launchAndFollow("/api/runs/spec",
            { corpus_id: currentCorpusId(), spec: text }, launchBtn);
        });
      });
    }

    // Une file de recettes, quelles qu'elles soient, part en un seul run ;
    // vide et sans corpus, c'est la démonstration.
    launchBtn.addEventListener("click", function () {
      if (queue.length && !currentCorpusId()) {
        resultEl.textContent = queueList.dataset.noCorpus || "";
        return;
      }
      if (missingSecrets()) {
        resultEl.textContent = queueList.dataset.secretMissing || "";
        return;
      }
      launchAndFollow("/api/runs", collectConfig(), launchBtn);
    });
  });
})();
