/*
 * wordApi.js — Lapisan akses dokumen Word (Office.js)
 * Menggabungkan kemampuan baca/edit dari: word-GPT-Plus, word-ai-redliner,
 * WordAgent, ollama-word-addin, ai-office-addin, WordCopilotChat.
 *
 * Semua fungsi async dan aman dipanggil dari taskpane.
 */
window.WordAPI = (function () {
  "use strict";

  function isReady() {
    return typeof Word !== "undefined" && typeof Office !== "undefined";
  }

  /* ---------- BACA ---------- */

  // Baca teks seleksi aktif
  async function getSelectedText() {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      sel.load("text");
      await context.sync();
      return sel.text || "";
    });
  }

  // Baca paragraf tempat kursor berada (paragraf pertama dari seleksi)
  async function getCurrentParagraph() {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      const paras = sel.paragraphs;
      paras.load("items/text");
      await context.sync();
      if (paras.items.length === 0) return "";
      return paras.items.map((p) => p.text).join("\n");
    });
  }

  // Baca seluruh dokumen
  async function getWholeDocument() {
    return Word.run(async (context) => {
      const body = context.document.body;
      body.load("text");
      await context.sync();
      return body.text || "";
    });
  }

  // Baca daftar paragraf (untuk agent: locate -> read)
  async function listParagraphs() {
    return Word.run(async (context) => {
      const paras = context.document.body.paragraphs;
      paras.load("items/text");
      await context.sync();
      return paras.items.map((p, i) => ({ index: i, text: p.text }));
    });
  }

  // Hitung kata pada seleksi (real-time, dari ollama-word-addin)
  async function getSelectionWordCount() {
    const t = await getSelectedText();
    const w = (t.trim().match(/\S+/g) || []).length;
    return { text: t, words: w, chars: t.length };
  }

  /* ---------- EDIT ---------- */

  // Ganti seleksi dengan teks baru (pola inti word-GPT-Plus)
  async function replaceSelection(newText) {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      sel.insertText(newText, Word.InsertLocation.replace);
      await context.sync();
      return true;
    });
  }

  // Sisipkan setelah seleksi
  async function appendAfterSelection(text) {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      sel.insertText("\n" + text, Word.InsertLocation.after);
      await context.sync();
      return true;
    });
  }

  // Sisipkan sebelum seleksi
  async function insertBeforeSelection(text) {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      sel.insertText(text + "\n", Word.InsertLocation.before);
      await context.sync();
      return true;
    });
  }

  // Tambah paragraf baru di akhir dokumen
  async function appendToDocument(text) {
    return Word.run(async (context) => {
      context.document.body.insertParagraph(text, Word.InsertLocation.end);
      await context.sync();
      return true;
    });
  }

  // Sisipkan di posisi kursor
  async function insertAtCursor(text) {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      sel.insertText(text, Word.InsertLocation.end);
      await context.sync();
      return true;
    });
  }

  /* ---------- CARI & GANTI (word-GPT-Plus / WordAgent) ---------- */

  async function searchAndReplace(query, replacement, opts) {
    opts = opts || {};
    return Word.run(async (context) => {
      const results = context.document.body.search(query, {
        matchCase: !!opts.matchCase,
        matchWholeWord: !!opts.matchWholeWord,
      });
      results.load("items");
      await context.sync();
      const count = results.items.length;
      results.items.forEach((r) =>
        r.insertText(replacement, Word.InsertLocation.replace)
      );
      await context.sync();
      return count;
    });
  }

  // Cari paragraf yang memuat query, kembalikan index+teks (agent: search_document)
  async function searchDocument(query) {
    return Word.run(async (context) => {
      const results = context.document.body.search(query, { matchCase: false });
      results.load("items/text");
      await context.sync();
      return results.items.map((r) => r.text);
    });
  }

  /* ---------- TRACK CHANGES / REDLINE (word-ai-redliner) ---------- */

  async function setTrackChanges(on) {
    return Word.run(async (context) => {
      const doc = context.document;
      doc.changeTrackingMode = on
        ? Word.ChangeTrackingMode.trackAll
        : Word.ChangeTrackingMode.off;
      await context.sync();
      return true;
    });
  }

  // Terapkan edit AI ke seleksi sebagai tracked change (nyalakan track -> replace -> matikan)
  async function replaceSelectionAsRedline(newText) {
    await setTrackChanges(true);
    await replaceSelection(newText);
    // biarkan track tetap menyala agar reviewer bisa accept/reject manual
    return true;
  }

  /* ---------- KOMENTAR ---------- */
  async function addCommentToSelection(commentText) {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      // API comment tersedia di WordApi 1.4+
      if (sel.insertComment) {
        sel.insertComment(commentText);
        await context.sync();
        return true;
      }
      return false;
    });
  }

  /* ---------- SISIP HTML (markdown -> format Word asli) ---------- */
  // Inti "powerful": render markdown jadi HTML lalu insertHtml supaya Word
  // membuat heading, tabel, list, bold sebagai format dokumen asli.

  // Ganti seluruh isi dokumen dengan HTML (untuk generate dokumen baru)
  async function setDocumentHtml(html) {
    return Word.run(async (context) => {
      const body = context.document.body;
      body.clear();
      body.insertHtml(html, Word.InsertLocation.start);
      await context.sync();
      return true;
    });
  }

  // Tambah HTML di akhir dokumen (streaming/append terformat)
  async function appendHtmlToDocument(html) {
    return Word.run(async (context) => {
      context.document.body.insertHtml(html, Word.InsertLocation.end);
      await context.sync();
      return true;
    });
  }

  // Sisip HTML di posisi kursor / ganti seleksi dengan HTML terformat
  async function insertHtmlAtSelection(html, replace) {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      sel.insertHtml(
        html,
        replace ? Word.InsertLocation.replace : Word.InsertLocation.after
      );
      await context.sync();
      return true;
    });
  }

  // Sisip satu persamaan (OOXML/OMML) di akhir dokumen -> jadi equation Word ASLI
  async function appendEquation(latex, displayMode) {
    const ooxml = window.EQ.buildEquationOoxml(latex, displayMode !== false);
    return Word.run(async (context) => {
      context.document.body.insertOoxml(ooxml, Word.InsertLocation.end);
      await context.sync();
      return true;
    });
  }

  // INTI: tulis markdown yang BISA mengandung rumus LaTeX ke dokumen.
  // Memecah konten jadi blok teks (markdown->HTML->insertHtml) dan blok rumus
  // (LaTeX->OMML->insertOoxml), lalu menyisipkannya berurutan di akhir dokumen
  // sehingga heading/tabel/list DAN equation sama-sama jadi format Word asli.
  // `clearFirst=true` mengganti seluruh dokumen (mode Buat Dokumen).
  async function insertMarkdownWithMath(markdown, clearFirst) {
    const hasMath = window.EQ && window.EQ.hasMath(markdown);

    // Jalur cepat: tidak ada rumus -> satu insertHtml saja.
    if (!hasMath) {
      const html = window.MD.toHtml(markdown);
      return Word.run(async (context) => {
        const body = context.document.body;
        if (clearFirst) body.clear();
        body.insertHtml(html, Word.InsertLocation.end);
        await context.sync();
        return true;
      });
    }

    // Ada rumus: pecah jadi segmen teks vs equation.
    const segs = window.EQ.splitMathSegments(markdown);
    return Word.run(async (context) => {
      const body = context.document.body;
      if (clearFirst) body.clear();
      for (let i = 0; i < segs.length; i++) {
        const s = segs[i];
        if (s.type === "eq") {
          const ooxml = window.EQ.buildEquationOoxml(s.value, s.display);
          body.insertOoxml(ooxml, Word.InsertLocation.end);
        } else {
          const txt = s.value;
          if (!txt || !txt.trim()) continue;
          body.insertHtml(window.MD.toHtml(txt), Word.InsertLocation.end);
        }
        // sync bertahap agar urutan sisip terjaga
        await context.sync();
      }
      return true;
    });
  }

  /* ---------- TABEL (word-GPT-Plus tools) ---------- */
  // rows: array of array of string. Sisipkan di posisi seleksi.
  async function insertTable(rows) {
    return Word.run(async (context) => {
      const sel = context.document.getSelection();
      const r = rows.length;
      const c = rows[0] ? rows[0].length : 0;
      sel.insertTable(r, c, Word.InsertLocation.after, rows);
      await context.sync();
      return true;
    });
  }

  return {
    isReady,
    getSelectedText,
    getCurrentParagraph,
    getWholeDocument,
    listParagraphs,
    getSelectionWordCount,
    replaceSelection,
    appendAfterSelection,
    insertBeforeSelection,
    appendToDocument,
    insertAtCursor,
    searchAndReplace,
    searchDocument,
    setTrackChanges,
    replaceSelectionAsRedline,
    addCommentToSelection,
    setDocumentHtml,
    appendHtmlToDocument,
    insertHtmlAtSelection,
    appendEquation,
    insertMarkdownWithMath,
    insertTable,
  };
})();
