/*
 * aiClient.js — Klien API OpenAI-compatible (streaming)
 * Default: PaperFull API (https://ai.otomasi.app/v1, model VIOLA-CHAT)
 * Mendukung custom endpoint/key/model lewat Settings.
 */
window.AIClient = (function () {
  "use strict";

  const DEFAULTS = {
    baseUrl: "https://ai.otomasi.app/v1",
    apiKey: "sk-ccfa926bc01cfa19-wruy62-243f58d1",
    model: "VIOLA-CHAT",
    temperature: 0.7,
  };

  const STORAGE_KEY = "viola_addin_settings";

  function getConfig() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      return Object.assign({}, DEFAULTS, saved);
    } catch (e) {
      return Object.assign({}, DEFAULTS);
    }
  }

  function saveConfig(cfg) {
    const merged = Object.assign(getConfig(), cfg);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
    return merged;
  }

  function resetConfig() {
    localStorage.removeItem(STORAGE_KEY);
    return getConfig();
  }

  // Bangun URL & header untuk lewat proxy server lokal (hindari CORS endpoint AI).
  // Set window.VIOLA_DIRECT = true untuk memaksa fetch langsung (mis. endpoint yang sudah ber-CORS).
  function buildRequest(targetPath) {
    const cfg = getConfig();
    const targetUrl = cfg.baseUrl.replace(/\/$/, "") + targetPath;
    const direct = !!window.VIOLA_DIRECT;
    if (direct) {
      return {
        url: targetUrl,
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + cfg.apiKey },
      };
    }
    return {
      url: "/proxy",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + cfg.apiKey,
        "X-Api-Key": cfg.apiKey,
        "X-Target-Url": targetUrl,
      },
    };
  }

  // Ambil daftar model dari endpoint /models (via proxy)
  async function listModels() {
    const r = buildRequest("/models");
    const res = await fetch(r.url, { headers: r.headers });
    if (!res.ok) throw new Error("Gagal ambil model: HTTP " + res.status);
    const data = await res.json();
    return (data.data || []).map((m) => m.id);
  }

  /*
   * chatStream — kirim messages, panggil onToken(delta) tiap potongan.
   * messages: [{role, content}]. Mengembalikan teks lengkap.
   */
  async function chatStream(messages, onToken, overrides) {
    const cfg = Object.assign(getConfig(), overrides || {});
    const r = buildRequest("/chat/completions");

    const res = await fetch(r.url, {
      method: "POST",
      headers: r.headers,
      body: JSON.stringify({
        model: cfg.model,
        messages: messages,
        temperature: cfg.temperature,
        stream: true,
      }),
    });

    if (!res.ok) {
      const errTxt = await res.text().catch(() => "");
      throw new Error("API error HTTP " + res.status + " " + errTxt.slice(0, 200));
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let full = "";
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // sisa baris belum lengkap
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith("data:")) continue;
        const payload = trimmed.slice(5).trim();
        if (payload === "[DONE]") continue;
        try {
          const json = JSON.parse(payload);
          const delta =
            (json.choices &&
              json.choices[0] &&
              json.choices[0].delta &&
              json.choices[0].delta.content) ||
            "";
          if (delta) {
            full += delta;
            if (onToken) onToken(delta, full);
          }
        } catch (e) {
          /* potongan JSON tak lengkap, abaikan */
        }
      }
    }
    return full;
  }

  // Versi non-stream (kembalikan teks penuh)
  async function chat(messages, overrides) {
    return chatStream(messages, null, overrides);
  }

  /*
   * chatWithTools — panggilan non-stream yang mengirim daftar `tools` (function
   * calling) dan mengembalikan message mentah dari API (mungkin berisi tool_calls).
   */
  async function chatWithTools(messages, tools, overrides) {
    const cfg = Object.assign(getConfig(), overrides || {});
    const r = buildRequest("/chat/completions");
    const res = await fetch(r.url, {
      method: "POST",
      headers: r.headers,
      body: JSON.stringify({
        model: cfg.model,
        messages: messages,
        temperature: cfg.temperature,
        tools: tools,
        tool_choice: "auto",
        stream: false,
      }),
    });
    if (!res.ok) {
      const errTxt = await res.text().catch(() => "");
      throw new Error("API error HTTP " + res.status + " " + errTxt.slice(0, 200));
    }
    const data = await res.json();
    return (data.choices && data.choices[0] && data.choices[0].message) || {};
  }

  /*
   * runAgent — LOOP AGENTIC. AI mengedit dokumen sendiri:
   *   1. kirim instruksi + daftar tool Word
   *   2. jika AI balas tool_calls -> jalankan tiap tool, kirim hasil kembali
   *   3. ulangi sampai AI berhenti memanggil tool (atau batas ronde tercapai)
   *
   * params:
   *   system, userPrompt : string
   *   tools              : definisi tool OpenAI (window.WordTools.definitions)
   *   executeTool(name,args) -> Promise<string>  (window.WordTools.execute)
   *   onStep(info)       : callback progres {type, name, args, result, text}
   *   maxRounds          : default 8
   */
  async function runAgent(opts) {
    const tools = opts.tools;
    const executeTool = opts.executeTool;
    const onStep = opts.onStep || function () {};
    const maxRounds = opts.maxRounds || 8;

    const messages = [
      { role: "system", content: opts.system },
      { role: "user", content: opts.userPrompt },
    ];

    let finalText = "";
    for (let round = 0; round < maxRounds; round++) {
      const msg = await chatWithTools(messages, tools, opts.overrides);
      const calls = msg.tool_calls || [];

      // Tidak ada tool call -> AI selesai, kembalikan teks akhir.
      if (!calls.length) {
        finalText = msg.content || "";
        onStep({ type: "final", text: finalText });
        return finalText;
      }

      // Catat pesan assistant (dengan tool_calls) ke riwayat.
      messages.push({
        role: "assistant",
        content: msg.content || "",
        tool_calls: calls,
      });

      // Jalankan tiap tool call secara berurutan, kirim hasil sbg role:tool.
      for (let i = 0; i < calls.length; i++) {
        const call = calls[i];
        let args = {};
        try { args = JSON.parse(call.function.arguments || "{}"); }
        catch (e) { args = {}; }
        onStep({ type: "call", name: call.function.name, args: args });

        let result;
        try { result = await executeTool(call.function.name, args); }
        catch (e) { result = "ERROR: " + (e && e.message ? e.message : e); }

        onStep({ type: "result", name: call.function.name, result: result });
        messages.push({
          role: "tool",
          tool_call_id: call.id,
          name: call.function.name,
          content: String(result),
        });
      }
    }
    // Batas ronde tercapai.
    onStep({ type: "final", text: finalText || "(selesai — batas langkah tercapai)" });
    return finalText || "Selesai (batas langkah agen tercapai).";
  }

  return {
    DEFAULTS,
    getConfig,
    saveConfig,
    resetConfig,
    listModels,
    chatStream,
    chat,
    chatWithTools,
    runAgent,
  };
})();
