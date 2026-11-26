/* Banc d'essai — le composeur : un catalogue de recettes.
 *
 * Lit GET /api/recipes, montre les formes nommées et leurs étapes, et pose
 * l'entrée choisie dans la file du banc (window.cinocQueue, posé par
 * benchmark.js). Le lancement part de benchmark.js, par POST /api/runs : un
 * seul bouton, une seule file, un seul suivi SSE.
 *
 * Chaque étape montre sa brique (choisissable si le rôle en propose plusieurs),
 * ses réglages requis, et les autres dans un pli — tous lus dans la
 * déclaration de la brique (PARAMS), aucun écrit ici. Une étape facultative
 * (entités nommées, export ALTO) se retient par sa case.
 *
 * Le serveur reste la source de vérité : il dit quelles briques tournent ici
 * (disponibilité, mode public) et ce que chacune accepte ; le client n'invente
 * aucune règle, il n'empêche que ce que le serveur refuserait.
 */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  ready(function () {
    var cards = document.getElementById("recipe-cards");
    var stepsEl = document.getElementById("recipe-steps");
    var addBtn = document.getElementById("recipe-add");
    var status = document.getElementById("recipe-status");
    var segBox = document.getElementById("seg-preview-box");
    if (!cards || !stepsEl || !addBtn || !status) return;
    var lang = document.documentElement.lang === "en" ? "en" : "fr";
    var catalog = [];
    var current = null;
    var models = {};
    var fieldSeq = 0;

    function say(key, extra) {
      status.textContent = (status.getAttribute("data-" + key) || "") +
        (extra ? " " + extra : "");
    }

    function text(key) {
      return stepsEl.getAttribute("data-" + key) || "";
    }

    function brickOf(step, kind) {
      for (var i = 0; i < step.bricks.length; i++) {
        if (step.bricks[i].kind === kind) return step.bricks[i];
      }
      return null;
    }

    function renderCards(recipes) {
      cards.textContent = "";
      recipes.forEach(function (recipe) {
        var id = "recipe-" + recipe.name;
        var card = el("label", "recipe-card");
        card.setAttribute("for", id);
        var input = el("input", "recipe-radio");
        input.type = "radio";
        input.name = "recipe";
        input.id = id;
        input.value = recipe.name;
        input.addEventListener("change", function () { select(recipe); });
        card.appendChild(input);
        var body = el("span", "recipe-text");
        body.appendChild(el("span", "recipe-title", recipe.title));
        body.appendChild(el("span", "recipe-desc", recipe.description));
        card.appendChild(body);
        cards.appendChild(card);
      });
    }

    function select(recipe) {
      current = recipe;
      stepsEl.textContent = "";
      recipe.steps.forEach(function (step, index) {
        stepsEl.appendChild(stepRow(step, index));
      });
      // L'aperçu des régions suit une recette qui segmente (benchmark.js lit
      // le segmenteur et son adresse dans les champs de l'étape).
      if (segBox) {
        segBox.hidden = !recipe.steps.some(function (s) {
          return s.role === "segmenter";
        });
      }
      sync();
    }

    // Une ligne par étape : le rôle en clair, la brique choisissable, ses
    // réglages ; une étape facultative s'ouvre par sa case.
    function stepRow(step, index) {
      var row = el("div", "recipe-step");
      var id = "recipe-step-" + step.step;
      var head = el("label", "recipe-step-head", (index + 1) + ". " + step.role_label);
      head.setAttribute("for", id);
      var body = el("div", "recipe-step-body");
      if (step.optional) {
        var toggle = el("input");
        toggle.type = "checkbox";
        toggle.setAttribute("data-optional", step.step);
        toggle.addEventListener("change", function () {
          body.hidden = !toggle.checked;
          sync();
        });
        var wrap = el("label", "recipe-step-head");
        wrap.appendChild(toggle);
        wrap.appendChild(document.createTextNode(
          " " + text("optional") + " " + step.role_label));
        row.appendChild(wrap);
        body.hidden = true;
      } else {
        row.appendChild(head);
      }
      var picker = el("select", "select");
      picker.id = id;
      picker.setAttribute("data-step", step.step);
      picker.setAttribute("data-role", step.role);
      step.bricks.forEach(function (brick) {
        var opt = el("option", "", brick.kind + (brick.available ? "" :
          " — " + text("unavailable") + " (" + brick.detail + ")"));
        opt.value = brick.kind;
        opt.disabled = !brick.available;
        opt.selected = brick.kind === step.default;
        picker.appendChild(opt);
      });
      // Défaut indisponible ici : la première brique qui tourne, s'il y en a.
      if (picker.selectedIndex < 0 || picker.options[picker.selectedIndex].disabled) {
        var first = Array.prototype.filter.call(picker.options, function (o) {
          return !o.disabled;
        })[0];
        picker.value = first ? first.value : "";
      }
      body.appendChild(picker);
      if (step.fanout) body.appendChild(el("span", "dropzone-meta", text("fanout")));
      var params = el("div", "recipe-params");
      body.appendChild(params);
      row.appendChild(body);
      picker.addEventListener("change", function () {
        renderParams(step, picker.value, params);
        sync();
      });
      renderParams(step, picker.value, params);
      return row;
    }

    function renderParams(step, kind, box) {
      box.textContent = "";
      var brick = brickOf(step, kind);
      if (!brick) return;
      var fold = el("details", "recipe-settings");
      fold.appendChild(el("summary", "dropzone-meta", text("settings")));
      brick.params.forEach(function (param) {
        var field = el("label", "comp-field");
        field.appendChild(el("span", "comp-label", param.label));
        var input = paramInput(param);
        input.setAttribute("data-param", param.name);
        input.setAttribute("data-type", param.type);
        input.setAttribute("data-step", step.step);
        input.addEventListener(input.type === "checkbox" ? "change" : "input", sync);
        field.appendChild(input);
        (param.required ? box : fold).appendChild(field);
      });
      if (fold.children.length > 1) box.appendChild(fold);
    }

    function paramInput(param) {
      var input;
      if (param.type === "bool") {
        input = el("input");
        input.type = "checkbox";
        input.checked = param.default === true;
        input.setAttribute("data-default", String(param.default === true));
        return input;
      }
      if (param.choices.length) {
        input = el("select", "select");
        if (!param.required && param.choices.indexOf("") < 0) param.choices.unshift("");
        param.choices.forEach(function (choice) {
          var label = choice === "" ? "—" : String(choice);
          if (choice === "" && param.default !== null) label += " " + text("default") + " " + param.default;
          var opt = el("option", "", label);
          opt.value = String(choice);
          input.appendChild(opt);
        });
        return input;
      }
      input = el(param.name === "prompt" ? "textarea" : "input", "input");
      if (input.tagName === "INPUT") {
        input.type = param.secret ? "password" : param.type === "str" ? "text" : "number";
        if (param.type === "float") input.step = "any";
      } else {
        input.rows = 3;
      }
      if (param.default !== null) input.placeholder = text("default") + " " + param.default;
      input.required = param.required;
      if (param.models_url) suggestModels(input, param.models_url);
      return input;
    }

    // Les modèles du fournisseur, demandés **en direct** (même origine, mis en
    // cache) : rien de codé ; liste indisponible → saisie libre, et le pourquoi.
    function suggestModels(input, url) {
      var listId = "recipe-models-" + (++fieldSeq);
      var list = el("datalist");
      list.id = listId;
      input.setAttribute("list", listId);
      var pending = models[url] || fetch(url).then(function (r) {
        return r.ok ? r.json() : { models: [] };
      }).catch(function () { return { models: [] }; });
      models[url] = pending;
      pending.then(function (data) {
        var names = (data.models || []).map(function (m) { return m.name; });
        names.forEach(function (name) {
          var opt = el("option");
          opt.value = name;
          list.appendChild(opt);
        });
        input.title = names.length ? names.length + " " + text("models") :
          text("models-none") + (data.unavailable ? " " + data.unavailable : "");
        if (input.parentNode) input.parentNode.appendChild(list);
      });
    }

    function value(input) {
      var type = input.getAttribute("data-type");
      if (type === "bool") {
        var on = input.checked;
        return String(on) === input.getAttribute("data-default") ? null : on;
      }
      var raw = input.value.trim();
      if (!raw) return null;
      return type === "int" || type === "float" ? Number(raw) : raw;
    }

    // La forme envoyée à POST /api/runs (une entrée de ``entries``), ou la
    // raison pour laquelle elle ne peut pas encore l'être.
    function collect() {
      var off = {};
      var optional = [];
      stepsEl.querySelectorAll("[data-optional]").forEach(function (box) {
        if (box.checked) optional.push(box.getAttribute("data-optional"));
        else off[box.getAttribute("data-optional")] = true;
      });
      var choices = {};
      var params = {};
      var pickers = stepsEl.querySelectorAll("select[data-role]");
      for (var i = 0; i < pickers.length; i++) {
        var step = pickers[i].getAttribute("data-step");
        if (off[step]) continue;
        if (!pickers[i].value) return { problem: ["unrunnable", step] };
        choices[step] = pickers[i].value;
      }
      var inputs = stepsEl.querySelectorAll("[data-param]");
      for (var j = 0; j < inputs.length; j++) {
        var owner = inputs[j].getAttribute("data-step");
        if (off[owner]) continue;
        var v = value(inputs[j]);
        var name = inputs[j].getAttribute("data-param");
        if (v === null && inputs[j].required) return { problem: ["missing", name] };
        if (v !== null) (params[owner] = params[owner] || {})[name] = v;
      }
      return {
        request: { recipe: current.name, choices: choices, params: params,
                   optional: optional },
      };
    }

    // Titre et chaîne d'une entrée, pour la file — aussi pour une entrée
    // importée d'une configuration (benchmark.js l'appelle).
    function describe(request) {
      var recipe = catalog.filter(function (r) { return r.name === request.recipe; })[0];
      if (!recipe) return { label: request.recipe, meta: "" };
      var chain = recipe.steps.filter(function (s) {
        return !s.optional || (request.optional || []).indexOf(s.step) >= 0;
      }).map(function (s) {
        var kind = (request.choices || {})[s.step] || s.default;
        var model = ((request.params || {})[s.step] || {}).model;
        return kind + (model ? " (" + model + ")" : "");
      });
      return { label: recipe.title, meta: chain.join(" → ") };
    }

    function sync() {
      if (!current) {
        addBtn.disabled = true;
        return;
      }
      var entry = collect();
      addBtn.disabled = !entry.request;
      if (entry.problem) say(entry.problem[0], entry.problem[1]);
      else status.textContent = "";
    }

    addBtn.addEventListener("click", function () {
      var entry = current && collect();
      if (!entry || !entry.request || !window.cinocQueue) return;
      window.cinocQueue.add(entry.request);
      say("added");
    });

    window.cinocRecipes = { describe: describe };

    say("loading");
    fetch("/api/recipes?lang=" + lang)
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        status.textContent = "";
        catalog = data.recipes || [];
        renderCards(catalog);
      })
      .catch(function () { say("error"); });
  });
})();
