/* Comparaison de deux runs — 100 % client, zéro réseau (rapport autonome).
 *
 * Lit les données CER du run courant (bloc JSON inerte embarqué), laisse le
 * visiteur charger un second RunResult JSON depuis son disque (FileReader,
 * plafond 50 Mo), calcule les deltas CER par moteur et les affiche dans un
 * bandeau sticky. Script STATIQUE (son sha256 est épinglé dans la CSP des
 * réponses /reports/). Aucune donnée n'est insérée via innerHTML (anti-XSS :
 * tout texte issu du fichier passe par textContent). */
(function () {
  "use strict";
  var MAX_BYTES = 50 * 1024 * 1024;
  var btn = document.getElementById("cinoc-compare-btn");
  var input = document.getElementById("cinoc-compare-file");
  var dataEl = document.getElementById("cinoc-compare-data");
  if (!btn || !input || !dataEl) return;

  var current;
  try {
    current = JSON.parse(dataEl.textContent) || {};
  } catch (e) {
    return;
  }
  var currentCer = current.cer || {};

  function cerMap(run) {
    var map = {};
    var pipelines = run && run.pipelines;
    if (!Array.isArray(pipelines)) return map;
    // L'agrégat principal n'est pas stocké : il se dérive de la politique
    // d'échec du run (exclude -> conditionnel, empty_page -> opérationnel).
    var policy = run.manifest && run.manifest.failure_policy;
    var key = policy === "empty_page" ? "operational_aggregate" : "conditional_aggregate";
    for (var i = 0; i < pipelines.length; i++) {
      var p = pipelines[i];
      if (!p || typeof p.pipeline !== "string" || !Array.isArray(p[key])) continue;
      for (var j = 0; j < p[key].length; j++) {
        var s = p[key][j];
        if (s && s.metric === "cer" && typeof s.value === "number" && isFinite(s.value)) {
          map[p.pipeline + " · " + (p.view || "")] = s.value;
        }
      }
    }
    return map;
  }

  function fmtDelta(x) {
    return (x > 0 ? "+" : "") + (x * 100).toFixed(2) + " pt";
  }

  function banner() {
    var el = document.getElementById("cinoc-compare-banner");
    if (!el) {
      el = document.createElement("div");
      el.id = "cinoc-compare-banner";
      document.body.appendChild(el);
    }
    return el;
  }

  function addRow(parent, key, delta) {
    var row = document.createElement("span");
    row.className =
      "cb-row " + (delta > 0 ? "worse" : delta < 0 ? "better" : "same");
    var k = document.createElement("span");
    k.className = "cb-key";
    k.textContent = key;
    var d = document.createElement("span");
    d.className = "cb-delta";
    d.textContent = fmtDelta(delta);
    row.appendChild(k);
    row.appendChild(d);
    parent.appendChild(row);
  }

  function render(otherMap) {
    var el = banner();
    el.textContent = "";
    var keys = Object.keys(currentCer).sort();
    var shown = 0;
    var title = document.createElement("span");
    title.className = "cb-title";
    title.textContent = "Δ CER (run chargé − ce rapport)";
    el.appendChild(title);
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      if (!(key in otherMap)) continue;
      addRow(el, key, otherMap[key] - currentCer[key]);
      shown++;
    }
    if (shown === 0) {
      el.textContent = "Aucun moteur commun à comparer.";
      el.className = "compare-banner empty";
    } else {
      el.className = "compare-banner";
    }
  }

  btn.addEventListener("click", function () {
    input.click();
  });
  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) return;
    if (file.size > MAX_BYTES) {
      window.alert("Fichier trop volumineux (> 50 Mo).");
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      var other;
      try {
        other = JSON.parse(String(reader.result));
      } catch (e) {
        window.alert("JSON invalide.");
        return;
      }
      render(cerMap(other));
    };
    reader.readAsText(file);
  });
})();
