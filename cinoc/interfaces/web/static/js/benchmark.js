/* Banc d'essai — composeur de benchmark et suivi SSE.
 *
 * Un seul brouillon de concurrent alimente une file visible. Le serveur reste
 * la source de vérité pour le lancement et les erreurs ; le client ne traduit
 * que les états HTTP en messages lisibles.
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

  // Aperçu de mise en page (mode hybride) : lance une segmentation sur le corpus
  // choisi et injecte le SVG des régions (rendu serveur). Remplace l'ancienne page
  // /segmentation — la visualisation vit désormais dans le lanceur.
  function wireSegPreview() {
    var btn = document.getElementById("seg-preview-btn");
    var container = document.getElementById("seg-preview");
    if (!btn || !container) return;
    var status = document.getElementById("seg-preview-status");
    var corpusSelect = document.getElementById("corpus-select");
    var segmenter = document.getElementById("draft-segmenter");
    var endpoint = document.getElementById("draft-seg-endpoint");
    var token = document.getElementById("draft-seg-token");

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
      var payload = {
        corpus_id: corpusId,
        segmenter: segmenter ? segmenter.value : "pp_doclayout",
      };
      if (payload.segmenter === "remote_segmenter") {
        if (endpoint && endpoint.value.trim()) payload.endpoint = endpoint.value.trim();
        if (token && token.value.trim()) payload.token = token.value.trim();
      }
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
    var addBtn = document.getElementById("add-competitor");
    var queueTpl = document.getElementById("queue-row-tpl");
    var queueList = document.getElementById("queue-list");
    var queueEmpty = document.getElementById("queue-empty");
    if (!launchBtn || !statusEl || !resultEl || !queueList || !queueTpl) return;

    var queue = [];
    var activeMode = "ocr_only";
    var modeButtons = document.querySelectorAll("[data-mode]");
    var draftFields = document.querySelectorAll("[data-show]");
    var draftOcr = document.getElementById("draft-ocr");
    var draftLlm = document.getElementById("draft-llm");
    var draftVlm = document.getElementById("draft-vlm");
    var draftSegmenter = document.getElementById("draft-segmenter");
    var draftRecognizer = document.getElementById("draft-recognizer");
    var draftSegEndpoint = document.getElementById("draft-seg-endpoint");
    var draftSegToken = document.getElementById("draft-seg-token");
    var draftSegEndpointField = document.getElementById("draft-seg-endpoint-field");
    var draftSegTokenField = document.getElementById("draft-seg-token-field");
    var draftModel = document.getElementById("draft-model");
    var draftPrompt = document.getElementById("draft-prompt");
    var draftPromptCurated = document.getElementById("draft-prompt-curated");
    var draftNer = document.getElementById("draft-ner");
    var draftNerModel = document.getElementById("draft-ner-model");
    var draftAlto = document.getElementById("draft-alto");
    var queueLabels = {
      ocr: queueList.getAttribute("data-label-ocr") || "OCR",
      ocrLlm: queueList.getAttribute("data-label-ocr-llm") || "OCR → LLM",
      ocrVlm: queueList.getAttribute("data-label-ocr-vlm") || "OCR → VLM",
      vlm: queueList.getAttribute("data-label-vlm") || "VLM",
      hybrid: queueList.getAttribute("data-label-hybrid") || "Hybride",
    };

    // Endpoint/jeton du segmenteur distant : visibles seulement en mode hybride
    // ET quand ``remote_segmenter`` est choisi (sinon ils n'ont aucun sens).
    function syncSegFields() {
      if (!draftSegmenter) return;
      var isRemote =
        activeMode === "hybrid" && draftSegmenter.value === "remote_segmenter";
      if (draftSegEndpointField) draftSegEndpointField.hidden = !isRemote;
      if (draftSegTokenField) draftSegTokenField.hidden = !isRemote;
    }
    if (draftSegmenter) draftSegmenter.addEventListener("change", syncSegFields);

    function currentCorpusId() {
      return corpusSelect && corpusSelect.value ? corpusSelect.value : null;
    }

    function applyQueryCorpus() {
      var corpusId = new URLSearchParams(window.location.search).get("corpus");
      if (corpusId && corpusSelect) corpusSelect.value = corpusId;
    }

    // Le champ « Modèle » pointe vers la datalist du fournisseur sélectionné
    // (ollama / mistral), qui n'existe que si le serveur a renvoyé des modèles.
    // Sinon : saisie libre. Rien de hardcodé — les options viennent du serveur.
    var modelCache = {};

    function applyDatalist(listId, count) {
      if (listId && count) draftModel.setAttribute("list", listId);
      else draftModel.removeAttribute("list");
      var hint = document.getElementById("model-hint");
      if (hint) {
        hint.textContent = count
          ? count + " modèle(s) suggéré(s) — clique pour choisir"
          : "";
      }
    }

    function fillApiList(models) {
      var dl = document.getElementById("api-model-list");
      if (!dl) return 0;
      dl.textContent = "";
      for (var i = 0; i < models.length; i++) {
        var opt = document.createElement("option");
        opt.value = models[i].name;
        if (models[i].vision) opt.label = "vision";
        dl.appendChild(opt);
      }
      return models.length;
    }

    function currentProvider() {
      if (activeMode === "text_only") return draftLlm && draftLlm.value;
      if (activeMode === "text_and_image" || activeMode === "zero_shot") {
        return draftVlm && draftVlm.value;
      }
      // En hybride, le « modèle » cible le reconnaisseur par bloc (utile aux VLM).
      if (activeMode === "hybrid") return draftRecognizer && draftRecognizer.value;
      return "";
    }

    function updateModelList() {
      if (!draftModel) return;
      var provider = currentProvider();
      // Modèles réellement installés (live) : datalists rendues côté serveur.
      if (provider === "ollama" || provider === "mistral") {
        var dl = document.getElementById(provider + "-models");
        applyDatalist(provider + "-models", dl ? dl.children.length : 0);
        return;
      }
      // openai/anthropic : pas de source live → liste canonique + capacité vision
      // via /api/models/{provider} (même origine ; mise en cache).
      if (provider === "openai" || provider === "anthropic") {
        if (modelCache[provider]) {
          applyDatalist("api-model-list", fillApiList(modelCache[provider]));
          return;
        }
        var asked = provider;
        fetch("/api/models/" + encodeURIComponent(provider))
          .then(function (r) {
            return r.ok ? r.json() : { models: [] };
          })
          .then(function (data) {
            modelCache[asked] = data.models || [];
            if (currentProvider() === asked) {
              applyDatalist("api-model-list", fillApiList(modelCache[asked]));
            }
          })
          .catch(function () {});
        return;
      }
      applyDatalist("", 0);
    }

    function setMode(mode) {
      activeMode = mode;
      for (var i = 0; i < modeButtons.length; i++) {
        var isActive = modeButtons[i].getAttribute("data-mode") === mode;
        modeButtons[i].classList.toggle("on", isActive);
        modeButtons[i].setAttribute("aria-selected", isActive ? "true" : "false");
      }
      for (var j = 0; j < draftFields.length; j++) {
        var shown = draftFields[j].getAttribute("data-show").split(" ");
        draftFields[j].hidden = shown.indexOf(mode) < 0;
      }
      syncSegFields();
      updateModelList();
    }

    function summarize(entry) {
      if (entry.mode === "ocr_only") {
        return {
          label: queueLabels.ocr,
          meta: entry.engine,
        };
      }
      if (entry.mode === "text_only") {
        return {
          label: queueLabels.ocrLlm,
          meta: entry.engine + " → " + entry.llm + (entry.model ? " · " + entry.model : ""),
        };
      }
      if (entry.mode === "text_and_image") {
        return {
          label: queueLabels.ocrVlm,
          meta: entry.engine + " → " + entry.llm + (entry.model ? " · " + entry.model : ""),
        };
      }
      if (entry.mode === "hybrid") {
        return {
          label: queueLabels.hybrid,
          meta:
            entry.segmenter + " → " + entry.engine +
            (entry.model ? " · " + entry.model : ""),
        };
      }
      return {
        label: queueLabels.vlm,
        meta: entry.engine + (entry.model ? " · " + entry.model : ""),
      };
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

    function buildDraft() {
      var model = draftModel && draftModel.value ? draftModel.value.trim() : "";
      var prompt = draftPrompt && draftPrompt.value ? draftPrompt.value.trim() : "";
      // Texte libre prioritaire : s'il est saisi, on ignore le prompt curé (le
      // serveur refuse d'ailleurs les deux à la fois).
      var promptName =
        !prompt && draftPromptCurated ? draftPromptCurated.value : "";
      var ner = !!(draftNer && draftNer.checked);
      var nerModel =
        ner && draftNerModel && draftNerModel.value
          ? draftNerModel.value.trim()
          : "";
      // ALTO : export tesseract uniquement (la case est masquée en zero_shot, sans
      // étape OCR) ; le serveur refuse l'option avec un autre moteur.
      var alto = !!(draftAlto && draftAlto.checked) && activeMode !== "zero_shot";
      if (activeMode === "ocr_only") {
        // En OCR seul, `model` = le modèle du moteur (kraken/pero/calamari : path ;
        // mistral_ocr : nom). Tesseract/Google/Azure l'ignorent.
        return {
          engine: draftOcr.value,
          mode: "ocr_only",
          model: model,
          ner: ner,
          nerModel: nerModel,
          alto: alto,
        };
      }
      if (activeMode === "text_only") {
        return {
          engine: draftOcr.value,
          mode: "text_only",
          llm: draftLlm.value,
          model: model,
          prompt: prompt,
          promptName: promptName,
          ner: ner,
          nerModel: nerModel,
          alto: alto,
        };
      }
      if (activeMode === "text_and_image") {
        return {
          engine: draftOcr.value,
          mode: "text_and_image",
          llm: draftVlm.value,
          model: model,
          prompt: prompt,
          promptName: promptName,
          ner: ner,
          nerModel: nerModel,
          alto: alto,
        };
      }
      if (activeMode === "hybrid") {
        // Hybride : segmenteur en tête, ``engine`` = reconnaisseur par bloc (OCR
        // ou VLM zero-shot). ``model``/``prompt`` ciblent le reconnaisseur.
        var seg = draftSegmenter ? draftSegmenter.value : "";
        var remote = seg === "remote_segmenter";
        return {
          engine: draftRecognizer ? draftRecognizer.value : "",
          mode: "hybrid",
          segmenter: seg,
          segmenterEndpoint:
            remote && draftSegEndpoint ? draftSegEndpoint.value.trim() : "",
          segmenterToken:
            remote && draftSegToken ? draftSegToken.value.trim() : "",
          model: model,
          prompt: prompt,
          promptName: promptName,
          ner: ner,
          nerModel: nerModel,
          alto: alto,
        };
      }
      return {
        engine: draftVlm.value,
        mode: "zero_shot",
        model: model,
        prompt: prompt,
        promptName: promptName,
        ner: ner,
        nerModel: nerModel,
        alto: false,
      };
    }

    function payloadCompetitors() {
      var out = [];
      for (var i = 0; i < queue.length; i++) {
        var entry = {};
        entry.engine = queue[i].engine;
        // ``ocr_only`` et ``hybrid`` n'ont pas de ``mode`` côté serveur (l'hybride
        // est signalé par ``segmenter``). Les autres portent leur PipelineMode.
        if (queue[i].mode !== "ocr_only" && queue[i].mode !== "hybrid") {
          entry.mode = queue[i].mode;
        }
        if (queue[i].segmenter) {
          entry.segmenter = queue[i].segmenter;
          if (queue[i].segmenterEndpoint) {
            entry.segmenter_endpoint = queue[i].segmenterEndpoint;
          }
          if (queue[i].segmenterToken) {
            entry.segmenter_token = queue[i].segmenterToken;
          }
        }
        if (queue[i].llm) entry.llm = queue[i].llm;
        if (queue[i].model) entry.model = queue[i].model;
        if (queue[i].prompt) entry.prompt = queue[i].prompt;
        else if (queue[i].promptName) entry.prompt_name = queue[i].promptName;
        if (queue[i].ner) {
          entry.ner = true;
          if (queue[i].nerModel) entry.ner_model = queue[i].nerModel;
        }
        if (queue[i].alto) entry.alto = true;
        out.push(entry);
      }
      return out;
    }

    // Config save/load — l'« état du formulaire » EST un LaunchRequest (même
    // schéma que le POST /api/runs). Export = blob JSON téléchargé (état courant,
    // 0 réseau) ; import = validé côté serveur (POST /api/runs/config) AVANT de
    // repeupler — un fichier malformé est rejeté net, jamais appliqué en silence.
    function collectConfig() {
      var cfg = { competitors: payloadCompetitors() };
      var corpusId = currentCorpusId();
      if (corpusId) cfg.corpus_id = corpusId;
      if (normalization && normalization.value) cfg.normalization = normalization.value;
      if (charExclude && charExclude.value) cfg.char_exclude = charExclude.value;
      if (metricProfile && metricProfile.value) cfg.metric_profile = metricProfile.value;
      return cfg;
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
      queue = [];
      var comps = cfg.competitors || [];
      for (var i = 0; i < comps.length; i++) {
        var c = comps[i];
        queue.push({
          // ``segmenter`` posé ⇒ concurrent hybride (mode interne « hybrid »,
          // jamais envoyé au serveur) ; sinon ``mode`` explicite ou OCR seul.
          engine: c.engine,
          mode: c.segmenter ? "hybrid" : c.mode || "ocr_only",
          segmenter: c.segmenter || "",
          segmenterEndpoint: c.segmenter_endpoint || "",
          segmenterToken: c.segmenter_token || "",
          llm: c.llm || "",
          model: c.model || "",
          prompt: c.prompt || "",
          promptName: c.prompt_name || "",
          ner: !!c.ner,
          nerModel: c.ner_model || "",
          alto: !!c.alto,
        });
      }
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

    // Lancer un run et le suivre : **un seul** chemin pour les deux formes de
    // run que la page sait démarrer (benchmark, post-correction). Elles ne
    // diffèrent que par leur route et leur charge utile ; dupliquer le POST, la
    // gestion d'erreur et l'abonnement SSE aurait fait diverger les deux au
    // premier correctif.
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

    for (var i = 0; i < modeButtons.length; i++) {
      modeButtons[i].addEventListener("click", function () {
        setMode(this.getAttribute("data-mode"));
      });
    }
    // Changer de fournisseur LLM/VLM met à jour la datalist du champ « Modèle ».
    if (draftLlm) draftLlm.addEventListener("change", updateModelList);
    if (draftVlm) draftVlm.addEventListener("change", updateModelList);
    setMode(activeMode);

    if (addBtn) {
      addBtn.addEventListener("click", function () {
        queue.push(buildDraft());
        renderQueue();
      });
    }
    renderQueue();

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

    launchBtn.addEventListener("click", function () {
      var payload = { competitors: payloadCompetitors() };
      var corpusId = currentCorpusId();
      if (corpusId) payload.corpus_id = corpusId;
      if (normalization && normalization.value) payload.normalization = normalization.value;
      if (charExclude && charExclude.value) payload.char_exclude = charExclude.value;
      if (metricProfile && metricProfile.value) payload.metric_profile = metricProfile.value;
      launchAndFollow("/api/runs", payload, launchBtn);
    });

    // Post-correction structurée : une **autre forme de run** (un ALTO déjà là
    // qu'on corrige), pas un concurrent de plus dans la file — donc sa propre
    // route et son propre bouton. Elle réutilise `subscribe` et
    // `reportTerminal` : le suivi SSE et le lien vers le rapport ne sont pas
    // réécrits une seconde fois.
    var correctBtn = document.getElementById("correct-launch");
    if (correctBtn) {
      var correctProducer = document.getElementById("correct-producer");
      var correctModel = document.getElementById("correct-model");
      var correctHost = document.getElementById("correct-host");

      function syncCorrectFields() {
        var ollama = correctProducer && correctProducer.value === "ollama";
        var wrap = document.getElementById("correct-ollama-fields");
        if (wrap) wrap.hidden = !ollama;
      }

      if (correctProducer) {
        correctProducer.addEventListener("change", syncCorrectFields);
        syncCorrectFields();
      }

      correctBtn.addEventListener("click", function () {
        var corpusId = currentCorpusId();
        if (!corpusId) {
          resultEl.textContent = correctBtn.dataset.noCorpus || "";
          return;
        }
        var payload = {
          corpus_id: corpusId,
          producer: correctProducer ? correctProducer.value : "rules",
        };
        if (correctModel && correctModel.value.trim()) {
          payload.model = correctModel.value.trim();
        }
        if (correctHost && correctHost.value.trim()) {
          payload.host = correctHost.value.trim();
        }
        launchAndFollow("/api/runs/correction", payload, correctBtn);
      });
    }

  });
})();
