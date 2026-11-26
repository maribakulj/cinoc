/* Banc d'essai — catalogue de recettes (couche 1 du composeur).
 *
 * Lit GET /api/recipes, montre les formes nommées et leurs étapes, et pose
 * l'entrée choisie dans la file du banc (window.cinocQueue, posé par
 * benchmark.js). Le lancement part de benchmark.js, par POST /api/runs/recipe :
 * un seul bouton, une seule file, un seul suivi SSE.
 *
 * Le serveur reste la source de vérité : il dit quelles briques tournent ici
 * (disponibilité, mode public) et ce que chacune exige ; le client n'invente
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
    var root = document.getElementById("recipe-picker");
    var cards = document.getElementById("recipe-cards");
    var stepsEl = document.getElementById("recipe-steps");
    var addBtn = document.getElementById("recipe-add");
    var status = document.getElementById("recipe-status");
    if (!root || !cards || !stepsEl || !addBtn || !status) return;
    var lang = document.documentElement.lang === "en" ? "en" : "fr";
    var current = null;

    function say(key, extra) {
      status.textContent = (status.getAttribute("data-" + key) || "") +
        (extra ? " " + extra : "");
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
        var text = el("span", "recipe-text");
        text.appendChild(el("span", "recipe-title", recipe.title));
        text.appendChild(el("span", "recipe-desc", recipe.description));
        card.appendChild(text);
        cards.appendChild(card);
      });
    }

    function select(recipe) {
      current = recipe;
      stepsEl.textContent = "";
      recipe.steps.forEach(function (step, index) {
        stepsEl.appendChild(stepRow(step, index));
      });
      sync();
    }

    // Une ligne par étape : le rôle en clair, la brique choisissable, et les
    // réglages **requis** de la brique choisie (les autres ont un défaut).
    function stepRow(step, index) {
      var row = el("div", "recipe-step");
      var id = "recipe-step-" + step.step;
      var head = el("label", "recipe-step-head", (index + 1) + ". " + step.role_label);
      head.setAttribute("for", id);
      row.appendChild(head);
      var picker = el("select", "select");
      picker.id = id;
      picker.setAttribute("data-step", step.step);
      step.bricks.forEach(function (brick) {
        var opt = el("option", "", brick.kind + (brick.available ? "" :
          " — " + stepsEl.getAttribute("data-unavailable") + " (" + brick.detail + ")"));
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
      row.appendChild(picker);
      if (step.fanout) {
        row.appendChild(el("span", "dropzone-meta", stepsEl.getAttribute("data-fanout")));
      }
      var params = el("div", "recipe-params");
      row.appendChild(params);
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
      brick.required.forEach(function (param) {
        var field = el("label", "comp-field");
        field.appendChild(el("span", "comp-label", param.label));
        var input;
        if (param.choices.length) {
          input = el("select", "select");
          param.choices.forEach(function (choice) {
            var opt = el("option", "", String(choice));
            opt.value = String(choice);
            input.appendChild(opt);
          });
        } else {
          input = el("input", "input");
          input.type = param.secret ? "password" : param.type === "str" ? "text" : "number";
          if (param.type === "float") input.step = "any";
        }
        input.required = true;
        input.setAttribute("data-param", param.name);
        input.setAttribute("data-type", param.type);
        input.setAttribute("data-step", step.step);
        input.addEventListener("input", sync);
        field.appendChild(input);
        box.appendChild(field);
      });
    }

    // La forme envoyée à POST /api/runs/recipe (une entrée de ``entries``), ou
    // la raison pour laquelle elle ne peut pas encore l'être.
    function collect() {
      var choices = {};
      var params = {};
      var chain = [];
      var pickers = stepsEl.querySelectorAll("select[data-step]:not([data-param])");
      for (var i = 0; i < pickers.length; i++) {
        var step = pickers[i].getAttribute("data-step");
        if (!pickers[i].value) return { problem: ["unrunnable", step] };
        choices[step] = pickers[i].value;
        chain.push(pickers[i].value);
      }
      var inputs = stepsEl.querySelectorAll("[data-param]");
      for (var j = 0; j < inputs.length; j++) {
        var raw = inputs[j].value.trim();
        var name = inputs[j].getAttribute("data-param");
        if (!raw) return { problem: ["missing", name] };
        var type = inputs[j].getAttribute("data-type");
        var value = type === "int" || type === "float" ? Number(raw) :
          type === "bool" ? raw === "true" : raw;
        var owner = inputs[j].getAttribute("data-step");
        (params[owner] = params[owner] || {})[name] = value;
      }
      return {
        request: { recipe: current.name, choices: choices, params: params },
        meta: chain.join(" → "),
      };
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
      window.cinocQueue.add({
        label: current.title,
        meta: entry.meta,
        request: entry.request,
      });
      say("added");
    });

    say("loading");
    fetch("/api/recipes?lang=" + lang)
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        status.textContent = "";
        renderCards(data.recipes || []);
      })
      .catch(function () { say("error"); });
  });
})();
