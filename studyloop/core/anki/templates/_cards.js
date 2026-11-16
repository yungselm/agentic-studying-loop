/* agentic-studying-loop (from rust-lang-kata): editor + line-diff + optional code walkthrough (with viz) */
(function () {
  var STORE_KEY = "anki_typed_code";

  function decode(b64) {
    if (!b64) return "";
    try { return decodeURIComponent(escape(window.atob(b64))); }
    catch (e) { return b64; }
  }

  function tabKey(cm) {
    if (cm.somethingSelected()) cm.execCommand("indentMore");
    else cm.replaceSelection("    ", "end");
  }

  function opts(lang, extra) {
    var base = {
      mode: lang || "text/plain",
      theme: "vscdark",
      lineNumbers: true,
      indentUnit: 4, tabSize: 4, indentWithTabs: false,
      matchBrackets: true, autoCloseBrackets: true,
      viewportMargin: Infinity,
      extraKeys: { "Tab": tabKey }
    };
    for (var k in (extra || {})) base[k] = extra[k];
    return base;
  }

  function rstrip(s) { return (s || "").replace(/\s+$/, ""); }
  function data() { return document.getElementById("cm-data"); }

  window.ankiCodeFront = function () {
    var d = data(); if (!d || typeof CodeMirror === "undefined") return;
    var lang = d.getAttribute("data-lang") || "text/plain";
    var starter = decode(d.getAttribute("data-starter"));
    var host = document.getElementById("editor"); if (!host) return;
    host.innerHTML = "";
    var cm = CodeMirror(host, opts(lang, { value: starter, autofocus: true }));
    function save() { try { sessionStorage.setItem(STORE_KEY, cm.getValue()); } catch (e) {} }
    save();
    cm.on("change", save);
    setTimeout(function () { cm.refresh(); cm.focus(); }, 60);
  };

  window.ankiCodeBack = function () {
    var d = data(); if (!d || typeof CodeMirror === "undefined") return;
    var lang = d.getAttribute("data-lang") || "text/plain";
    var solution = decode(d.getAttribute("data-solution"));
    var typed = "";
    try { typed = sessionStorage.getItem(STORE_KEY) || ""; } catch (e) {}

    var host = document.getElementById("editor"), cm = null;
    if (host) {
      host.innerHTML = "";
      cm = CodeMirror(host, opts(lang, { value: typed, readOnly: "nocursor" }));
    }

    var ut = typed.replace(/\r\n/g, "\n").split("\n");
    var st = solution.replace(/\r\n/g, "\n").split("\n");
    var n = Math.max(ut.length, st.length), wrong = 0;
    for (var i = 0; i < n; i++) {
      if (rstrip(ut[i]) !== rstrip(st[i])) {
        wrong++;
        if (cm && i < ut.length) cm.addLineClass(i, "background", "wrong-line");
      }
    }
    if (cm) setTimeout(function () { cm.refresh(); }, 60);

    var solCm = renderReadonly("solution", solution, lang);

    var status = document.getElementById("status");
    if (status) {
      if (wrong === 0) {
        status.textContent = "✓ Correct"; status.className = "status ok";
      } else {
        status.textContent = wrong + (wrong === 1 ? " line differs" : " lines differ");
        status.className = "status bad";
      }
    }

    var wt = decode(d.getAttribute("data-walkthrough"));
    if (wt && solCm) setupWalkthrough(solCm, wt);
  };

  function renderReadonly(id, code, lang) {
    var host = document.getElementById(id);
    if (!host || typeof CodeMirror === "undefined") return null;
    host.innerHTML = "";
    var cm = CodeMirror(host, opts(lang, { value: code, readOnly: "nocursor" }));
    setTimeout(function () { cm.refresh(); }, 60);
    return cm;
  }

  window.ankiCodeShow = function () {
    var d = data(); if (!d) return;
    var lang = d.getAttribute("data-lang") || "text/plain";
    var code = decode(d.getAttribute("data-solution"));
    if (code) renderReadonly("solution", code, lang);
  };

  // 1-based "a-b,c" -> 0-based line indices
  function parseRanges(str) {
    var nums = [];
    str.split(",").forEach(function (part) {
      part = part.trim();
      if (!part) return;
      var seg = part.split("-");
      if (seg.length === 2) {
        var a = parseInt(seg[0], 10), b = parseInt(seg[1], 10);
        for (var x = a; x <= b; x++) nums.push(x - 1);
      } else {
        var v = parseInt(part, 10);
        if (!isNaN(v)) nums.push(v - 1);
      }
    });
    return nums;
  }

  // Walkthrough field. Block mode (steps separated by a line of "===") supports
  // an optional leading "@idea" block (plain-English core idea + HTML) and, per
  // step, "lineRange | caption" followed by optional HTML viz. Simple mode is one
  // "lineRange | caption" per line (no idea, no viz).
  function parseWalkthrough(text) {
    text = text.replace(/\r\n/g, "\n");
    var idea = "", steps = [];
    var blockMode = /^\s*===\s*$/m.test(text) || /^\s*@idea\s*$/im.test(text);
    function processBlock(block) {
      var lines = block.split("\n");
      var first = -1;
      for (var i = 0; i < lines.length; i++) { if (lines[i].trim()) { first = i; break; } }
      if (first < 0) return;
      if (lines[first].trim().toLowerCase() === "@idea") {
        idea = lines.slice(first + 1).join("\n").trim();
        return;
      }
      var hi = -1;
      for (var j = first; j < lines.length; j++) {
        if (lines[j].trim() && lines[j].indexOf("|") >= 0) { hi = j; break; }
      }
      if (hi < 0) return;
      var head = lines[hi], bar = head.indexOf("|");
      steps.push({
        lines: parseRanges(head.slice(0, bar)),
        caption: head.slice(bar + 1).trim(),
        viz: lines.slice(hi + 1).join("\n").trim()
      });
    }
    if (blockMode) {
      text.split(/^\s*===\s*$/m).forEach(processBlock);
    } else {
      text.split("\n").forEach(function (line) {
        if (!line.trim()) return;
        var bar = line.indexOf("|");
        if (bar < 0) return;
        steps.push({ lines: parseRanges(line.slice(0, bar)), caption: line.slice(bar + 1).trim(), viz: "" });
      });
    }
    return { idea: idea, steps: steps };
  }

  function setupWalkthrough(cm, text) {
    var parsed = parseWalkthrough(text);
    var ideaEl = document.getElementById("wt-idea");
    if (ideaEl) ideaEl.innerHTML = parsed.idea || "";
    var steps = parsed.steps;
    var controls = document.getElementById("wt-controls");
    var capEl = document.getElementById("wt-caption");
    var vizEl = document.getElementById("wt-viz");
    var lblEl = document.getElementById("wt-label");
    var prev = document.getElementById("wt-prev");
    var next = document.getElementById("wt-next");
    if (!steps.length) {
      [controls, capEl, vizEl].forEach(function (el) { if (el) el.style.display = "none"; });
      return;
    }
    var cur = 0, shown = [];
    function render() {
      shown.forEach(function (ln) { cm.removeLineClass(ln, "background", "wt-line"); });
      var lc = cm.lineCount();
      shown = steps[cur].lines.filter(function (ln) { return ln >= 0 && ln < lc; });
      shown.forEach(function (ln) { cm.addLineClass(ln, "background", "wt-line"); });
      if (capEl) capEl.textContent = steps[cur].caption;
      if (vizEl) vizEl.innerHTML = steps[cur].viz || "";
      if (lblEl) lblEl.textContent = (cur + 1) + " / " + steps.length;
      if (prev) prev.disabled = cur === 0;
      if (next) next.disabled = cur === steps.length - 1;
      cm.refresh();
    }
    if (prev) prev.onclick = function () { if (cur > 0) { cur--; render(); } };
    if (next) next.onclick = function () { if (cur < steps.length - 1) { cur++; render(); } };
    render();
  }
})();
