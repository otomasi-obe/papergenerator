/*
 * taskpane.js - Logika utama UI PaperFull Word
 */
(function () {
  "use strict";

  var lastResult = "";
  var busy = false;

  // ---------- Office init ----------
  if (typeof Office !== "undefined") {
    Office.onReady(function (info) {
      if (info.host === Office.HostType.Word) {
        init();
      } else {
        init(); // tetap init agar UI muncul saat dev di browser
      }
    });
  } else {
    window.addEventListener("DOMContentLoaded", init);
  }

  function $(id) { return document.getElementById(id); }

  function init() {
    renderActions();
    bindEvents();
    refreshWordCount();
    addMsg("ai", "Halo! Saya PaperFull Word. Pilih sumber teks, klik aksi cepat, atau ketik instruksi. Hasil bisa langsung diterapkan ke dokumen.");
  }

  // ---------- Quick action chips ----------
  function renderActions() {
    var box = $("actions");
    box.innerHTML = "";
    Prompts.presets.forEach(function (p) {
      var b = document.createElement("button");
      b.className = "action-chip";
      b.textContent = (p.icon ? p.icon + " " : "") + p.label;
      b.title = p.label;
      b.onclick = function () { runPreset(p); };
      box.appendChild(b);
    });
  }

  function bindEvents() {
    $("btnSend").onclick = onSend;
    $("userInput").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { onSend(); }
    });
    $("scopeSel").addEventListener("change", refreshWordCount);

    // apply buttons
    document.querySelectorAll(".apply-btn").forEach(function (b) {
      b.onclick = function () { applyResult(b.getAttribute("data-apply")); };
    });

    // settings
    $("btnSettings").onclick = openSettings;
    $("btnCancelCfg").onclick = closeSettings;
    $("btnSaveCfg").onclick = saveSettings;
    $("btnResetCfg").onclick = resetSettings;
    $("btnLoadModels").onclick = loadModels;
    $("cfgTemp").addEventListener("input", function () {
      $("tempVal").textContent = $("cfgTemp").value;
    });
    $("cfgModelSel").addEventListener("change", function () {
      if ($("cfgModelSel").value) $("cfgModel").value = $("cfgModelSel").value;
    });
  }

  // ---------- Ambil konteks sesuai scope ----------
  async function getContext() {
    if (!WordAPI.isReady()) return "";
    var scope = $("scopeSel").value;
    try {
      if (scope === "selection") return await WordAPI.getSelectedText();
      if (scope === "paragraph") return await WordAPI.getCurrentParagraph();
      if (scope === "document") return await WordAPI.getWholeDocument();
      return "";
    } catch (e) { return ""; }
  }

  async function refreshWordCount() {
    if (!WordAPI.isReady()) { $("wordCount").textContent = ""; return; }
    try {
      var info = await WordAPI.getSelectionWordCount();
      $("wordCount").textContent = info.words + " kata terpilih";
    } catch (e) { $("wordCount").textContent = ""; }
  }

  // ---------- Jalankan preset ----------
  async function runPreset(preset) {
    if (busy) return;

    // Preset agen: AI mengedit dokumen sendiri lewat tool calling.
    if (preset.isAgent) {
      var instr = $("userInput").value.trim();
      if (!instr) {
        addMsg("err", "Ketik instruksi edit dulu (mis. 'ganti semua kata motor jadi mesin, tebalkan judul'), lalu klik " + preset.label + ".");
        $("userInput").focus();
        return;
      }
      $("userInput").value = "";
      addMsg("user", preset.icon + " " + preset.label + ": " + instr);
      // Sertakan konteks seleksi bila ada
      var sctx = await getContext();
      var fullInstr = instr;
      if (sctx) fullInstr = "Teks yang sedang diseleksi pengguna:\n\"\"\"\n" + sctx + "\n\"\"\"\n\nInstruksi: " + instr;
      await runAgentEdit(preset.system, fullInstr);
      return;
    }

    // Preset "noContext" (mis. Buat Dokumen): topik diambil dari kotak input,
    // bukan dari seleksi dokumen.
    if (preset.noContext) {
      var topic = $("userInput").value.trim();
      if (!topic) {
        addMsg("err", "Ketik topik/instruksi dokumen di kotak input dulu, lalu klik " + preset.label + ".");
        $("userInput").focus();
        return;
      }
      $("userInput").value = "";
      addMsg("user", preset.icon + " " + preset.label + ": " + topic);
      await streamAI(preset.system, preset.build(topic), preset.apply);
      return;
    }

    var ctx = await getContext();
    if (preset.apply !== "chat" && !ctx) {
      addMsg("err", "Tidak ada teks pada sumber '" + $("scopeSel").value + "'. Pilih/seleksi teks dulu.");
      return;
    }
    var userPrompt = preset.build(ctx || "");
    addMsg("user", preset.icon + " " + preset.label);
    await streamAI(preset.system, userPrompt, preset.apply);
  }

  // ---------- Kirim chat manual ----------
  async function onSend() {
    if (busy) return;
    var text = $("userInput").value.trim();
    if (!text) return;
    $("userInput").value = "";

    var ctx = await getContext();
    var system = "Anda PaperFull Word, asisten penulisan di dalam Microsoft Word. Jawab ringkas dan berguna dalam bahasa pengguna.";
    var prompt = text;
    if (ctx) {
      prompt = "Konteks dokumen:\n\"\"\"\n" + ctx + "\n\"\"\"\n\nInstruksi: " + text;
    }
    addMsg("user", text);
    await streamAI(system, prompt, "chat");
  }

  // ---------- Streaming ke AI ----------
  async function streamAI(system, userPrompt, applyMode) {
    busy = true;
    setBusy(true);
    var messages = [
      { role: "system", content: system },
      { role: "user", content: userPrompt },
    ];
    var bubble = addMsg("ai", "");
    bubble.classList.add("typing");
    try {
      var full = await AIClient.chatStream(messages, function (delta, acc) {
        bubble.querySelector(".body").textContent = acc;
        scrollChat();
      });
      bubble.classList.remove("typing");
      lastResult = full;
      // Render balasan sebagai HTML terformat di panel (preview persis seperti yang masuk ke Word)
      try {
        bubble.querySelector(".body").innerHTML = MD.toHtml(full);
      } catch (e) { /* biarkan teks apa adanya */ }
      scrollChat();
      // tampilkan apply bar; sarankan "Tulis ke dokumen" untuk konten panjang/terformat
      var suggested = applyMode;
      if (applyMode === "chat") {
        suggested = /(^|\n)#{1,6}\s|\n\s*[-*]\s|\|.*\|/.test(full) ? "docFormatted" : "appendFormatted";
      }
      showApplyBar(suggested);
    } catch (e) {
      bubble.classList.remove("typing");
      bubble.classList.add("err");
      bubble.querySelector(".body").textContent = "Error: " + e.message;
    } finally {
      busy = false;
      setBusy(false);
    }
  }

  // ---------- Agen edit: AI mengedit dokumen sendiri via tool calling ----------
  async function runAgentEdit(system, userPrompt) {
    if (!WordAPI.isReady()) {
      addMsg("err", "Agen Edit butuh dijalankan di dalam Word (bukan browser biasa).");
      return;
    }
    busy = true;
    setBusy(true);
    // Panel langkah-langkah agen
    var bubble = addMsg("ai", "");
    var body = bubble.querySelector(".body");
    var steps = document.createElement("div");
    steps.className = "agent-steps";
    body.appendChild(steps);
    var summary = document.createElement("div");
    summary.className = "agent-summary";
    body.appendChild(summary);

    function addStep(txt, cls) {
      var d = document.createElement("div");
      d.className = "agent-step " + (cls || "");
      d.textContent = txt;
      steps.appendChild(d);
      scrollChat();
      return d;
    }
    addStep("🤖 Agen mulai bekerja...", "muted");

    // Wrapper executeTool: intercept ask_user -> tampilkan prompt interaktif & tunggu jawaban.
    function executeToolWrapped(name, args) {
      if (name === "ask_user") {
        return askUserInline(args, addStep);
      }
      return WordTools.execute(name, args);
    }

    try {
      var finalText = await AIClient.runAgent({
        system: system,
        userPrompt: userPrompt,
        tools: WordTools.definitions,
        executeTool: executeToolWrapped,
        maxRounds: 12,
        onStep: function (info) {
          if (info.type === "call") {
            if (info.name === "ask_user") return; // tampilan khusus di handler
            var label = toolLabel(info.name, info.args);
            addStep("⚙ " + label, "call");
          } else if (info.type === "result") {
            addStep("✓ " + info.result, "ok");
          } else if (info.type === "final" && info.text) {
            try { summary.innerHTML = MD.toHtml(info.text); }
            catch (e) { summary.textContent = info.text; }
          }
        },
      });
      lastResult = finalText || "";
      if (!finalText) summary.textContent = "Selesai.";
      refreshWordCount();
      flashStatus("Agen selesai mengedit dokumen.");
    } catch (e) {
      addStep("Error: " + e.message, "err");
    } finally {
      busy = false;
      setBusy(false);
    }
  }

  // Tanya pengguna secara interaktif di dalam panel; kembalikan Promise<string> jawaban.
  function askUserInline(args, addStep) {
    return new Promise(function (resolve) {
      var wrap = document.createElement("div");
      wrap.className = "ask-user";
      var q = document.createElement("div");
      q.className = "ask-q";
      q.textContent = "❓ " + (args.question || "Mohon konfirmasi");
      wrap.appendChild(q);
      if (args.recommendation) {
        var rec = document.createElement("div");
        rec.className = "ask-rec";
        rec.textContent = "💡 Rekomendasi: " + args.recommendation;
        wrap.appendChild(rec);
      }
      var done = false;
      function finish(answer) {
        if (done) return;
        done = true;
        wrap.querySelectorAll("button, input").forEach(function (el) { el.disabled = true; });
        addStep("↳ Jawaban: " + answer, "ok");
        resolve("Jawaban pengguna: " + answer);
      }
      var btnRow = document.createElement("div");
      btnRow.className = "ask-btns";
      // Tombol terima rekomendasi
      var recBtn = document.createElement("button");
      recBtn.className = "ask-btn primary";
      recBtn.textContent = "Pakai rekomendasi";
      recBtn.onclick = function () { finish(args.recommendation || "ikuti rekomendasi"); };
      btnRow.appendChild(recBtn);
      // Opsi (bila ada)
      (args.options || []).forEach(function (opt) {
        var b = document.createElement("button");
        b.className = "ask-btn";
        b.textContent = opt;
        b.onclick = function () { finish(opt); };
        btnRow.appendChild(b);
      });
      wrap.appendChild(btnRow);
      // Input jawaban bebas
      var inRow = document.createElement("div");
      inRow.className = "ask-input-row";
      var inp = document.createElement("input");
      inp.type = "text";
      inp.placeholder = "atau ketik jawaban Anda...";
      inp.onkeydown = function (e) { if (e.key === "Enter" && inp.value.trim()) finish(inp.value.trim()); };
      var send = document.createElement("button");
      send.className = "ask-btn";
      send.textContent = "Kirim";
      send.onclick = function () { if (inp.value.trim()) finish(inp.value.trim()); };
      inRow.appendChild(inp);
      inRow.appendChild(send);
      wrap.appendChild(inRow);

      var stepsBox = document.querySelector(".agent-steps:last-of-type") || document.body;
      stepsBox.appendChild(wrap);
      scrollChat();
      inp.focus();
    });
  }

  // Label ramah untuk tiap tool call
  function toolLabel(name, args) {
    switch (name) {
      case "get_document_content": return "Membaca isi dokumen";
      case "get_selected_text": return "Membaca teks terpilih";
      case "search_and_replace": return "Mengganti '" + (args.find || "") + "' → '" + (args.replace || "") + "'";
      case "replace_selection": return "Mengganti seleksi";
      case "delete_text": return "Menghapus '" + (args.find || "") + "'";
      case "insert_paragraph": return "Menyisipkan paragraf" + (args.style ? " (" + args.style + ")" : "");
      case "append_text": return "Menambah teks di akhir";
      case "format_text": return "Memformat teks" + (args.find ? " '" + args.find + "'" : " seleksi");
      case "apply_style": return "Menerapkan style " + (args.style || "") + (args.find ? " ke '" + args.find + "'" : "");
      case "insert_table": return "Menyisipkan tabel";
      case "insert_list": return "Menyisipkan daftar";
      case "insert_equation": return "Menyisipkan rumus: " + (args.latex || "");
      case "insert_markdown": return "Menyisipkan blok terformat";
      case "insert_page_break": return "Menyisipkan page break";
      case "clear_document": return "Mengosongkan dokumen";
      case "find_text": return "Mencari '" + (args.search_text || "") + "'";
      case "insert_comment": return "Menambah komentar" + (args.on ? " pada '" + args.on + "'" : "");
      case "get_comments": return "Membaca komentar";
      case "delete_comment": return "Menghapus komentar #" + args.index;
      case "reply_to_comment": return "Membalas komentar #" + args.index;
      case "set_header": return "Mengatur header";
      case "set_footer": return "Mengatur footer";
      case "insert_footnote": return "Menyisipkan catatan kaki";
      case "insert_endnote": return "Menyisipkan catatan akhir";
      case "insert_bookmark": return "Menambah bookmark '" + (args.name || "") + "'";
      case "go_to_bookmark": return "Menuju bookmark '" + (args.name || "") + "'";
      case "insert_toc": return "Menyisipkan Daftar Isi";
      case "toggle_track_changes": return (args.enabled ? "Menyalakan" : "Mematikan") + " Track Changes";
      case "insert_section_break": return "Menyisipkan section break";
      case "set_page_margins": return "Mengatur margin halaman";
      case "get_table_info": return "Membaca info tabel";
      case "update_table_cell": return "Mengubah sel tabel";
      case "insert_image": return "Menyisipkan gambar";
      case "list_styles": return "Melihat daftar style";
      case "ask_user": return "Bertanya ke pengguna";
      default: return name;
    }
  }

  // ---------- Terapkan hasil ke dokumen ----------
  async function applyResult(mode) {
    if (!lastResult) return;
    if (mode === "copy") {
      try { await navigator.clipboard.writeText(lastResult); flashStatus("Disalin."); }
      catch (e) { flashStatus("Gagal menyalin."); }
      return;
    }
    if (!WordAPI.isReady()) {
      addMsg("err", "Word API tidak tersedia (sedang di browser, bukan di Word).");
      return;
    }
    try {
      if (mode === "docFormatted") {
        // Markdown + rumus LaTeX -> heading/tabel/list jadi HTML, rumus jadi OMML (equation Word asli)
        await WordAPI.insertMarkdownWithMath(lastResult, false);
        flashStatus("Ditulis ke dokumen (terformat + rumus).");
      } else if (mode === "appendFormatted") {
        await WordAPI.insertMarkdownWithMath(lastResult, false);
        flashStatus("Disisipkan terformat + rumus.");
      } else if (mode === "replace") {
        await WordAPI.replaceSelection(lastResult);
        flashStatus("Seleksi diganti.");
      } else if (mode === "redline") {
        await WordAPI.replaceSelectionAsRedline(lastResult);
        flashStatus("Diterapkan sebagai track changes.");
      }
      refreshWordCount();
    } catch (e) {
      addMsg("err", "Gagal menerapkan: " + e.message);
    }
  }

  function showApplyBar(suggested) {
    var bar = $("applyBar");
    bar.classList.remove("hidden");
    // highlight tombol yang disarankan preset
    bar.querySelectorAll(".apply-btn").forEach(function (b) {
      b.style.fontWeight = (b.getAttribute("data-apply") === suggested) ? "700" : "400";
    });
  }

  // ---------- UI helpers ----------
  function addMsg(role, text) {
    var chat = $("chat");
    var div = document.createElement("div");
    div.className = "msg " + role;
    var r = document.createElement("div");
    r.className = "role";
    r.textContent = role === "user" ? "Anda" : (role === "err" ? "Error" : "PaperFull");
    var body = document.createElement("div");
    body.className = "body";
    body.textContent = text;
    div.appendChild(r);
    div.appendChild(body);
    chat.appendChild(div);
    scrollChat();
    return div;
  }

  function scrollChat() { var c = $("chat"); c.scrollTop = c.scrollHeight; }
  function setBusy(b) { $("btnSend").disabled = b; }
  function flashStatus(msg) {
    var el = addMsg("ai", msg);
    setTimeout(function () { el.style.opacity = "0.5"; }, 1500);
  }

  // ---------- Settings ----------
  function openSettings() {
    var cfg = AIClient.getConfig();
    $("cfgBaseUrl").value = cfg.baseUrl;
    $("cfgApiKey").value = cfg.apiKey;
    $("cfgModel").value = cfg.model;
    $("cfgTemp").value = cfg.temperature;
    $("tempVal").textContent = cfg.temperature;
    $("cfgStatus").textContent = "";
    $("settingsModal").classList.remove("hidden");
  }
  function closeSettings() { $("settingsModal").classList.add("hidden"); }

  function saveSettings() {
    var model = $("cfgModel").value.trim() || $("cfgModelSel").value || "VIOLA-CHAT";
    AIClient.saveConfig({
      baseUrl: $("cfgBaseUrl").value.trim(),
      apiKey: $("cfgApiKey").value.trim(),
      model: model,
      temperature: parseFloat($("cfgTemp").value),
    });
    $("cfgStatus").textContent = "Tersimpan.";
    setTimeout(closeSettings, 600);
  }

  function resetSettings() {
    var cfg = AIClient.resetConfig();
    $("cfgBaseUrl").value = cfg.baseUrl;
    $("cfgApiKey").value = cfg.apiKey;
    $("cfgModel").value = cfg.model;
    $("cfgTemp").value = cfg.temperature;
    $("tempVal").textContent = cfg.temperature;
    $("cfgStatus").textContent = "Direset ke default.";
  }

  async function loadModels() {
    $("cfgStatus").textContent = "Memuat model...";
    // pakai nilai field saat ini untuk listModels
    AIClient.saveConfig({ baseUrl: $("cfgBaseUrl").value.trim(), apiKey: $("cfgApiKey").value.trim() });
    try {
      var models = await AIClient.listModels();
      var sel = $("cfgModelSel");
      sel.innerHTML = '<option value="">- pilih -</option>';
      models.forEach(function (m) {
        var o = document.createElement("option");
        o.value = m; o.textContent = m;
        sel.appendChild(o);
      });
      $("cfgStatus").textContent = models.length + " model dimuat.";
    } catch (e) {
      $("cfgStatus").textContent = "Gagal: " + e.message;
    }
  }

})();
