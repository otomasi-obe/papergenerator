/*
 * wordTools.js — Tool editing dokumen Word yang bisa dipanggil AI (function calling).
 * Inti "agentic editing": AI memanggil tool ini dalam loop untuk mengedit dokumen
 * sendiri (cari/ganti, format, sisip di lokasi tepat, tabel, rumus, dll).
 * Di-port & disederhanakan dari deepseek-word-addin (49 tool -> ~18 tool berdampak).
 */
window.WordTools = (function () {
  "use strict";

  // Mutex: serialkan operasi Word. Tanpa ini, tool call paralel berebut posisi
  // body yang sama -> struktur dokumen teracak/terbalik.
  var _lock = Promise.resolve();
  function withLock(fn) {
    var release;
    var prev = _lock;
    _lock = new Promise(function (res) { release = res; });
    return prev.then(function () {
      return Promise.resolve().then(fn).finally(function () { release(); });
    });
  }

  function hexColor(c) { return c ? String(c).replace(/^#/, "") : c; }

  // ---- Definisi tool (skema OpenAI function calling) ----
  var definitions = [
    { type: "function", function: {
      name: "get_document_content",
      description: "Baca seluruh isi teks dokumen saat ini. Gunakan untuk memahami isi sebelum mengedit.",
      parameters: { type: "object", properties: {} } } },
    { type: "function", function: {
      name: "get_selected_text",
      description: "Baca teks yang sedang diseleksi pengguna.",
      parameters: { type: "object", properties: {} } } },
    { type: "function", function: {
      name: "search_and_replace",
      description: "Cari semua kemunculan teks dan ganti. Untuk edit menyeluruh di dokumen.",
      parameters: { type: "object", properties: {
        find: { type: "string", description: "Teks yang dicari" },
        replace: { type: "string", description: "Teks pengganti" },
        match_case: { type: "boolean", description: "Cocokkan huruf besar/kecil (default false)" }
      }, required: ["find", "replace"] } } },
    { type: "function", function: {
      name: "replace_selection",
      description: "Ganti teks yang sedang diseleksi dengan teks baru.",
      parameters: { type: "object", properties: {
        text: { type: "string" } }, required: ["text"] } } },
    { type: "function", function: {
      name: "delete_text",
      description: "Hapus semua kemunculan teks tertentu dari dokumen.",
      parameters: { type: "object", properties: {
        find: { type: "string" } }, required: ["find"] } } },
    { type: "function", function: {
      name: "insert_paragraph",
      description: "Sisipkan paragraf baru dengan format opsional (style heading, bold, ukuran, rata, warna).",
      parameters: { type: "object", properties: {
        text: { type: "string" },
        location: { type: "string", enum: ["Start", "End"], description: "Posisi sisip (default End)" },
        style: { type: "string", description: "Style bawaan Word, mis. 'Heading1','Heading2','Title','Normal'" },
        alignment: { type: "string", enum: ["left", "center", "right", "justified"] },
        font_size: { type: "number" },
        bold: { type: "boolean" },
        italic: { type: "boolean" },
        font_family: { type: "string" },
        color: { type: "string", description: "Hex warna, mis. #1a1a1a" }
      }, required: ["text"] } } },
    { type: "function", function: {
      name: "append_text",
      description: "Tambahkan teks di akhir dokumen (tanpa format khusus).",
      parameters: { type: "object", properties: {
        text: { type: "string" } }, required: ["text"] } } },
    { type: "function", function: {
      name: "format_text",
      description: "Terapkan format (bold/italic/underline/ukuran/warna) pada teks yang cocok, atau pada seleksi bila 'find' kosong.",
      parameters: { type: "object", properties: {
        find: { type: "string", description: "Teks target; kosongkan untuk pakai seleksi" },
        bold: { type: "boolean" }, italic: { type: "boolean" }, underline: { type: "boolean" },
        font_size: { type: "number" }, color: { type: "string" }, font_family: { type: "string" }
      }, required: [] } } },
    { type: "function", function: {
      name: "apply_style",
      description: "Terapkan style bawaan Word (mis. Heading1) ke teks yang cocok atau ke seleksi.",
      parameters: { type: "object", properties: {
        find: { type: "string", description: "Teks target; kosongkan untuk seleksi" },
        style: { type: "string", description: "mis. 'Heading1','Heading2','Title','Quote','Normal'" }
      }, required: ["style"] } } }
  ];

  // Tambahan definisi tool: tabel, list, rumus, page break, dokumen
  definitions.push(
    { type: "function", function: {
      name: "insert_table",
      description: "Sisipkan tabel di akhir dokumen. Baris pertama dianggap header.",
      parameters: { type: "object", properties: {
        rows: { type: "array", description: "Array baris; tiap baris array string sel",
          items: { type: "array", items: { type: "string" } } }
      }, required: ["rows"] } } },
    { type: "function", function: {
      name: "insert_list",
      description: "Sisipkan daftar berpoin atau bernomor di akhir dokumen.",
      parameters: { type: "object", properties: {
        items: { type: "array", items: { type: "string" } },
        ordered: { type: "boolean", description: "true=bernomor, false=poin" }
      }, required: ["items"] } } },
    { type: "function", function: {
      name: "insert_equation",
      description: "Sisipkan persamaan matematika ASLI Word dari LaTeX (mis. n = \\\\frac{120 f}{P}).",
      parameters: { type: "object", properties: {
        latex: { type: "string", description: "Ekspresi LaTeX tanpa tanda $" },
        display: { type: "boolean", description: "true=rumus baris sendiri (default true)" }
      }, required: ["latex"] } } },
    { type: "function", function: {
      name: "insert_markdown",
      description: "Sisipkan blok Markdown (boleh berisi heading, tabel, list, dan rumus $$..$$) terformat di akhir dokumen.",
      parameters: { type: "object", properties: {
        markdown: { type: "string" } }, required: ["markdown"] } } },
    { type: "function", function: {
      name: "insert_page_break",
      description: "Sisipkan page break di akhir dokumen.",
      parameters: { type: "object", properties: {} } } },
    { type: "function", function: {
      name: "clear_document",
      description: "Hapus SELURUH isi dokumen. Hati-hati, gunakan hanya bila diminta menulis ulang total.",
      parameters: { type: "object", properties: {} } } }
  );

  // ---- Handler: jalankan satu tool, kembalikan ringkasan teks utk AI ----
  var handlers = {
    get_document_content: function () {
      return Word.run(function (ctx) {
        var body = ctx.document.body;
        body.load("text");
        return ctx.sync().then(function () {
          return "ISI DOKUMEN:\n" + (body.text || "(kosong)");
        });
      });
    },
    get_selected_text: function () {
      return Word.run(function (ctx) {
        var sel = ctx.document.getSelection();
        sel.load("text");
        return ctx.sync().then(function () {
          return "SELEKSI: " + (sel.text || "(tidak ada seleksi)");
        });
      });
    },
    search_and_replace: function (a) {
      return Word.run(function (ctx) {
        var results = ctx.document.body.search(a.find, { matchCase: !!a.match_case });
        results.load("items");
        return ctx.sync().then(function () {
          var n = results.items.length;
          for (var i = 0; i < n; i++) results.items[i].insertText(a.replace, Word.InsertLocation.replace);
          return ctx.sync().then(function () {
            return "Mengganti " + n + " kemunculan '" + a.find + "' -> '" + a.replace + "'.";
          });
        });
      });
    },
    replace_selection: function (a) {
      return Word.run(function (ctx) {
        ctx.document.getSelection().insertText(a.text, Word.InsertLocation.replace);
        return ctx.sync().then(function () { return "Seleksi diganti."; });
      });
    },
    delete_text: function (a) {
      return Word.run(function (ctx) {
        var results = ctx.document.body.search(a.find, { matchCase: false });
        results.load("items");
        return ctx.sync().then(function () {
          var n = results.items.length;
          for (var i = 0; i < n; i++) results.items[i].insertText("", Word.InsertLocation.replace);
          return ctx.sync().then(function () { return "Menghapus " + n + " kemunculan '" + a.find + "'."; });
        });
      });
    }
  };

  // Handler lanjutan: insert/format/style/tabel/list/rumus/markdown
  handlers.insert_paragraph = function (a) {
    return Word.run(function (ctx) {
      var loc = (a.location === "Start") ? Word.InsertLocation.start : Word.InsertLocation.end;
      var p = ctx.document.body.insertParagraph(a.text, loc);
      if (a.style) { try { p.styleBuiltIn = a.style; } catch (e) { try { p.style = a.style; } catch (e2) {} } }
      if (a.alignment) p.alignment = (a.alignment === "center" ? "Centered" : a.alignment.charAt(0).toUpperCase() + a.alignment.slice(1));
      if (a.font_size !== undefined) p.font.size = a.font_size;
      if (a.bold !== undefined) p.font.bold = a.bold;
      if (a.italic !== undefined) p.font.italic = a.italic;
      if (a.font_family) p.font.name = a.font_family;
      if (a.color) p.font.color = hexColor(a.color);
      return ctx.sync().then(function () { return "Paragraf disisipkan" + (a.style ? " (style " + a.style + ")" : "") + "."; });
    });
  };
  handlers.append_text = function (a) {
    return Word.run(function (ctx) {
      ctx.document.body.insertParagraph(a.text, Word.InsertLocation.end);
      return ctx.sync().then(function () { return "Teks ditambahkan di akhir."; });
    });
  };
  handlers.format_text = function (a) {
    return Word.run(function (ctx) {
      function applyTo(range) {
        if (a.bold !== undefined) range.font.bold = a.bold;
        if (a.italic !== undefined) range.font.italic = a.italic;
        if (a.underline !== undefined) range.font.underline = a.underline ? "Single" : "None";
        if (a.font_size !== undefined) range.font.size = a.font_size;
        if (a.color) range.font.color = hexColor(a.color);
        if (a.font_family) range.font.name = a.font_family;
      }
      if (a.find) {
        var results = ctx.document.body.search(a.find, { matchCase: false });
        results.load("items");
        return ctx.sync().then(function () {
          for (var i = 0; i < results.items.length; i++) applyTo(results.items[i]);
          return ctx.sync().then(function () { return "Format diterapkan ke " + results.items.length + " kemunculan."; });
        });
      } else {
        applyTo(ctx.document.getSelection());
        return ctx.sync().then(function () { return "Format diterapkan ke seleksi."; });
      }
    });
  };
  handlers.apply_style = function (a) {
    return Word.run(function (ctx) {
      function styleIt(range) { try { range.styleBuiltIn = a.style; } catch (e) { try { range.style = a.style; } catch (e2) {} } }
      if (a.find) {
        var results = ctx.document.body.search(a.find, { matchCase: false });
        results.load("items");
        return ctx.sync().then(function () {
          for (var i = 0; i < results.items.length; i++) styleIt(results.items[i].paragraphs.getFirst());
          return ctx.sync().then(function () { return "Style " + a.style + " diterapkan ke " + results.items.length + " kemunculan."; });
        });
      } else {
        styleIt(ctx.document.getSelection().paragraphs.getFirst());
        return ctx.sync().then(function () { return "Style " + a.style + " diterapkan ke seleksi."; });
      }
    });
  };
  handlers.insert_table = function (a) {
    return Word.run(function (ctx) {
      var rows = a.rows || [];
      if (!rows.length) return "Tabel kosong, dilewati.";
      var nCol = rows[0].length;
      var t = ctx.document.body.insertTable(rows.length, nCol, Word.InsertLocation.end, rows);
      try { t.styleBuiltIn = "GridTable4_Accent1"; } catch (e) {}
      return ctx.sync().then(function () { return "Tabel " + rows.length + "x" + nCol + " disisipkan."; });
    });
  };
  handlers.insert_list = function (a) {
    return Word.run(function (ctx) {
      var items = a.items || [];
      if (!items.length) return "List kosong.";
      var first = ctx.document.body.insertParagraph(items[0], Word.InsertLocation.end);
      var list = first.startNewList();
      list.load("id");
      return ctx.sync().then(function () {
        for (var i = 1; i < items.length; i++) {
          var p = ctx.document.body.insertParagraph(items[i], Word.InsertLocation.end);
          p.attachToList(list.id, 0);
        }
        return ctx.sync().then(function () { return (a.ordered ? "Daftar bernomor " : "Daftar poin ") + items.length + " item disisipkan."; });
      });
    });
  };
  handlers.insert_equation = function (a) {
    var ooxml = window.EQ.buildEquationOoxml(a.latex, a.display !== false);
    return Word.run(function (ctx) {
      ctx.document.body.insertOoxml(ooxml, Word.InsertLocation.end);
      return ctx.sync().then(function () { return "Persamaan disisipkan: " + a.latex; });
    });
  };
  handlers.insert_markdown = function (a) {
    return window.WordAPI.insertMarkdownWithMath(a.markdown, false).then(function () {
      return "Blok markdown terformat disisipkan.";
    });
  };
  handlers.insert_page_break = function () {
    return Word.run(function (ctx) {
      ctx.document.body.insertBreak(Word.BreakType.page, Word.InsertLocation.end);
      return ctx.sync().then(function () { return "Page break disisipkan."; });
    });
  };
  handlers.clear_document = function () {
    return Word.run(function (ctx) {
      ctx.document.body.clear();
      return ctx.sync().then(function () { return "Dokumen dikosongkan."; });
    });
  };


  // ===== TOOL LANJUTAN: cakup semua komponen Word =====
  definitions.push(
    { type: "function", function: {
      name: "find_text",
      description: "Cari teks dan laporkan jumlah kemunculan (tidak mengubah dokumen). Berguna utk verifikasi sebelum edit.",
      parameters: { type: "object", properties: {
        search_text: { type: "string" }, match_case: { type: "boolean" }, match_whole_word: { type: "boolean" }
      }, required: ["search_text"] } } },
    { type: "function", function: {
      name: "insert_comment",
      description: "Sisipkan komentar (anotasi) pada teks yang cocok atau pada seleksi.",
      parameters: { type: "object", properties: {
        text: { type: "string", description: "Isi komentar" },
        on: { type: "string", description: "Teks target; kosongkan untuk pakai seleksi" }
      }, required: ["text"] } } },
    { type: "function", function: {
      name: "get_comments",
      description: "Baca semua komentar di dokumen (penulis, isi, jumlah balasan).",
      parameters: { type: "object", properties: {} } } },
    { type: "function", function: {
      name: "delete_comment",
      description: "Hapus komentar berdasarkan indeks (0-based dari get_comments).",
      parameters: { type: "object", properties: { index: { type: "number" } }, required: ["index"] } } },
    { type: "function", function: {
      name: "reply_to_comment",
      description: "Balas komentar berdasarkan indeks.",
      parameters: { type: "object", properties: { index: { type: "number" }, text: { type: "string" } }, required: ["index", "text"] } } },
    { type: "function", function: {
      name: "set_header",
      description: "Atur teks header halaman (section pertama).",
      parameters: { type: "object", properties: {
        text: { type: "string" }, alignment: { type: "string", enum: ["Left", "Center", "Right"] }
      }, required: ["text"] } } },
    { type: "function", function: {
      name: "set_footer",
      description: "Atur teks footer halaman (section pertama).",
      parameters: { type: "object", properties: {
        text: { type: "string" }, alignment: { type: "string", enum: ["Left", "Center", "Right"] }
      }, required: ["text"] } } },
    { type: "function", function: {
      name: "insert_footnote",
      description: "Sisipkan catatan kaki (footnote) pada seleksi.",
      parameters: { type: "object", properties: { text: { type: "string" } }, required: ["text"] } } },
    { type: "function", function: {
      name: "insert_endnote",
      description: "Sisipkan catatan akhir (endnote) pada seleksi.",
      parameters: { type: "object", properties: { text: { type: "string" } }, required: ["text"] } } },
    { type: "function", function: {
      name: "insert_bookmark",
      description: "Sisipkan bookmark pada seleksi untuk menandai lokasi.",
      parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] } } },
    { type: "function", function: {
      name: "go_to_bookmark",
      description: "Navigasi/seleksi ke bookmark yang sudah dibuat.",
      parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] } } },
    { type: "function", function: {
      name: "insert_toc",
      description: "Sisipkan Daftar Isi. Cara terbaik: kirim array 'chapters' berisi judul bab yang direncanakan (cepat, tak perlu scan). Tiap item {title, level:1|2|3}.",
      parameters: { type: "object", properties: {
        title: { type: "string", description: "Judul TOC, default 'Daftar Isi'" },
        chapters: { type: "array", items: { type: "object", properties: {
          title: { type: "string" }, level: { type: "number", enum: [1, 2, 3] } }, required: ["title"] } },
        location: { type: "string", enum: ["Start", "End"] }
      }, required: [] } } },
    { type: "function", function: {
      name: "toggle_track_changes",
      description: "Nyalakan/matikan mode Track Changes (rekam revisi).",
      parameters: { type: "object", properties: { enabled: { type: "boolean" } }, required: ["enabled"] } } },
    { type: "function", function: {
      name: "insert_section_break",
      description: "Sisipkan section break.",
      parameters: { type: "object", properties: {
        type: { type: "string", enum: ["NextPage", "Continuous", "EvenPage", "OddPage"] } }, required: ["type"] } } },
    { type: "function", function: {
      name: "set_page_margins",
      description: "Atur margin halaman semua section (poin; 1 inci = 72 pt).",
      parameters: { type: "object", properties: {
        top: { type: "number" }, bottom: { type: "number" }, left: { type: "number" }, right: { type: "number" } }, required: [] } } },
    { type: "function", function: {
      name: "get_table_info",
      description: "Baca info semua tabel di dokumen (jumlah, baris, kolom).",
      parameters: { type: "object", properties: {} } } },
    { type: "function", function: {
      name: "update_table_cell",
      description: "Ubah isi satu sel tabel (tabel ke-N, baris, kolom; semua 0-based).",
      parameters: { type: "object", properties: {
        table_index: { type: "number" }, row: { type: "number" }, column: { type: "number" }, text: { type: "string" } },
        required: ["table_index", "row", "column", "text"] } } },
    { type: "function", function: {
      name: "insert_image",
      description: "Sisipkan gambar dari URL pada seleksi (lebar/tinggi opsional, dalam poin).",
      parameters: { type: "object", properties: {
        url: { type: "string" }, width: { type: "number" }, height: { type: "number" } }, required: ["url"] } } },
    { type: "function", function: {
      name: "list_styles",
      description: "Daftar style bawaan Word yang umum dipakai untuk apply_style.",
      parameters: { type: "object", properties: {} } } },
    { type: "function", function: {
      name: "ask_user",
      description: "TANYA pengguna ketika Anda ragu atau ada beberapa pilihan masuk akal. WAJIB sertakan rekomendasi default Anda. Pakai HANYA bila keputusan benar-benar memengaruhi hasil; untuk hal sepele putuskan sendiri. Jawaban pengguna akan dikembalikan kepada Anda.",
      parameters: { type: "object", properties: {
        question: { type: "string", description: "Pertanyaan jelas untuk pengguna" },
        recommendation: { type: "string", description: "Rekomendasi default Anda bila pengguna tidak menjawab spesifik" },
        options: { type: "array", items: { type: "string" }, description: "Opsi pilihan (opsional)" }
      }, required: ["question", "recommendation"] } } }
  );


  // ---- Handler tool lanjutan ----
  handlers.find_text = function (a) {
    return Word.run(function (ctx) {
      var r = ctx.document.body.search(a.search_text, { matchCase: !!a.match_case, matchWholeWord: !!a.match_whole_word });
      r.load("items");
      return ctx.sync().then(function () {
        return "Ditemukan " + r.items.length + " kemunculan '" + a.search_text + "'.";
      });
    });
  };
  handlers.insert_comment = function (a) {
    return Word.run(function (ctx) {
      if (a.on) {
        var r = ctx.document.body.search(a.on, { matchCase: false });
        r.load("items");
        return ctx.sync().then(function () {
          if (!r.items.length) return "Teks '" + a.on + "' tidak ditemukan.";
          r.items[0].insertComment(a.text);
          return ctx.sync().then(function () { return "Komentar disisipkan pada '" + a.on + "'."; });
        });
      }
      ctx.document.getSelection().insertComment(a.text);
      return ctx.sync().then(function () { return "Komentar disisipkan pada seleksi."; });
    });
  };
  handlers.get_comments = function () {
    return Word.run(function (ctx) {
      var c = ctx.document.body.getComments();
      c.load("items");
      return ctx.sync().then(function () {
        for (var i = 0; i < c.items.length; i++) { c.items[i].load(["authorName", "content"]); }
        return ctx.sync().then(function () {
          if (!c.items.length) return "Tidak ada komentar.";
          var out = c.items.map(function (x, i) { return i + ". [" + x.authorName + "] " + x.content; });
          return "Komentar (" + c.items.length + "):\n" + out.join("\n");
        });
      });
    });
  };
  handlers.delete_comment = function (a) {
    return Word.run(function (ctx) {
      var c = ctx.document.body.getComments();
      c.load("items");
      return ctx.sync().then(function () {
        if (a.index < 0 || a.index >= c.items.length) return "ERROR: indeks " + a.index + " di luar jangkauan.";
        c.items[a.index].delete();
        return ctx.sync().then(function () { return "Komentar " + a.index + " dihapus."; });
      });
    });
  };
  handlers.reply_to_comment = function (a) {
    return Word.run(function (ctx) {
      var c = ctx.document.body.getComments();
      c.load("items");
      return ctx.sync().then(function () {
        if (a.index < 0 || a.index >= c.items.length) return "ERROR: indeks di luar jangkauan.";
        c.items[a.index].reply(a.text);
        return ctx.sync().then(function () { return "Balasan ditambahkan ke komentar " + a.index + "."; });
      });
    });
  };
  handlers.set_header = function (a) {
    return Word.run(function (ctx) {
      var h = ctx.document.sections.getFirst().getHeader("Primary");
      var p = h.insertParagraph(a.text, Word.InsertLocation.end);
      if (a.alignment) p.alignment = a.alignment;
      return ctx.sync().then(function () { return "Header diatur: '" + a.text + "'."; });
    });
  };
  handlers.set_footer = function (a) {
    return Word.run(function (ctx) {
      var f = ctx.document.sections.getFirst().getFooter("Primary");
      var p = f.insertParagraph(a.text, Word.InsertLocation.end);
      if (a.alignment) p.alignment = a.alignment;
      return ctx.sync().then(function () { return "Footer diatur: '" + a.text + "'."; });
    });
  };
  handlers.insert_footnote = function (a) {
    return Word.run(function (ctx) {
      ctx.document.getSelection().insertFootnote(a.text);
      return ctx.sync().then(function () { return "Catatan kaki disisipkan."; });
    });
  };
  handlers.insert_endnote = function (a) {
    return Word.run(function (ctx) {
      ctx.document.getSelection().insertEndnote(a.text);
      return ctx.sync().then(function () { return "Catatan akhir disisipkan."; });
    });
  };
  handlers.insert_bookmark = function (a) {
    return Word.run(function (ctx) {
      ctx.document.getSelection().insertBookmark(a.name);
      return ctx.sync().then(function () { return "Bookmark '" + a.name + "' disisipkan."; });
    });
  };
  handlers.go_to_bookmark = function (a) {
    return Word.run(function (ctx) {
      ctx.document.getBookmarkRange(a.name).select();
      return ctx.sync().then(function () { return "Menuju bookmark '" + a.name + "'."; });
    });
  };


  handlers.insert_toc = function (a) {
    var title = a.title || "Daftar Isi";
    var location = a.location === "Start" ? "Start" : "End";
    var chapters = a.chapters || [];
    return Word.run(function (ctx) {
      var body = ctx.document.body;
      function applyEntry(p, level) {
        try { p.style = "Normal"; } catch (e) {}
        p.font.size = level === 1 ? 12 : 11;
        p.font.bold = level === 1;
        if (level === 2) p.leftIndent = 24;
        if (level === 3) p.leftIndent = 48;
        p.spaceBefore = level === 1 ? 8 : 3;
        p.spaceAfter = level === 1 ? 4 : 2;
      }
      var entries = chapters.map(function (c) { return { level: Number(c.level) || 1, text: String(c.title || "") }; });
      if (location === "Start") {
        var rev = entries.slice().reverse();
        for (var i = 0; i < rev.length; i++) applyEntry(body.insertParagraph(rev[i].text, Word.InsertLocation.start), rev[i].level);
        var tpS = body.insertParagraph(title, Word.InsertLocation.start);
        try { tpS.styleBuiltIn = "Heading1"; } catch (e) {}
        tpS.alignment = "Centered";
      } else {
        var tpE = body.insertParagraph(title, Word.InsertLocation.end);
        try { tpE.styleBuiltIn = "Heading1"; } catch (e) {}
        tpE.alignment = "Centered";
        for (var j = 0; j < entries.length; j++) applyEntry(body.insertParagraph(entries[j].text, Word.InsertLocation.end), entries[j].level);
      }
      return ctx.sync().then(function () {
        return entries.length ? "Daftar Isi disisipkan (" + entries.length + " entri)." : "Judul Daftar Isi disisipkan (tanpa entri).";
      });
    });
  };
  handlers.toggle_track_changes = function (a) {
    return Word.run(function (ctx) {
      ctx.document.changeTrackingMode = a.enabled ? Word.ChangeTrackingMode.trackAll : Word.ChangeTrackingMode.off;
      return ctx.sync().then(function () { return "Track changes " + (a.enabled ? "dinyalakan" : "dimatikan") + "."; });
    });
  };
  handlers.insert_section_break = function (a) {
    return Word.run(function (ctx) {
      ctx.document.getSelection().insertBreak("Section" + (a.type || "NextPage"), Word.InsertLocation.after);
      return ctx.sync().then(function () { return "Section break (" + (a.type || "NextPage") + ") disisipkan."; });
    });
  };
  handlers.set_page_margins = function (a) {
    var top = a.top !== undefined ? a.top : 72, bottom = a.bottom !== undefined ? a.bottom : 72,
        left = a.left !== undefined ? a.left : 90, right = a.right !== undefined ? a.right : 90;
    return Word.run(function (ctx) {
      var s = ctx.document.sections; s.load("items");
      return ctx.sync().then(function () {
        for (var i = 0; i < s.items.length; i++) {
          s.items[i].pageMargin.top = top; s.items[i].pageMargin.bottom = bottom;
          s.items[i].pageMargin.left = left; s.items[i].pageMargin.right = right;
        }
        return ctx.sync().then(function () { return "Margin diatur: atas=" + top + " bawah=" + bottom + " kiri=" + left + " kanan=" + right + " pt."; });
      });
    });
  };
  handlers.get_table_info = function () {
    return Word.run(function (ctx) {
      var t = ctx.document.body.tables; t.load("items");
      return ctx.sync().then(function () {
        for (var i = 0; i < t.items.length; i++) t.items[i].load("rowCount,values");
        return ctx.sync().then(function () {
          if (!t.items.length) return "Tidak ada tabel.";
          var out = t.items.map(function (x, i) {
            var cols = x.values && x.values[0] ? x.values[0].length : 0;
            return "Tabel " + i + ": " + x.rowCount + " baris x " + cols + " kolom";
          });
          return out.join("\n");
        });
      });
    });
  };
  handlers.update_table_cell = function (a) {
    return Word.run(function (ctx) {
      var t = ctx.document.body.tables; t.load("items");
      return ctx.sync().then(function () {
        if (a.table_index < 0 || a.table_index >= t.items.length) return "ERROR: tabel " + a.table_index + " tidak ada.";
        var cell = t.items[a.table_index].getCell(a.row, a.column);
        cell.value = a.text;
        return ctx.sync().then(function () { return "Sel tabel[" + a.table_index + "](" + a.row + "," + a.column + ") diubah."; });
      });
    });
  };
  handlers.insert_image = function (a) {
    return fetch(a.url).then(function (r) { return r.blob(); }).then(function (blob) {
      return new Promise(function (resolve, reject) {
        var fr = new FileReader();
        fr.onloadend = function () { resolve(String(fr.result).split(",")[1]); };
        fr.onerror = reject;
        fr.readAsDataURL(blob);
      });
    }).then(function (b64) {
      return Word.run(function (ctx) {
        var pic = ctx.document.getSelection().insertInlinePictureFromBase64(b64, Word.InsertLocation.end);
        if (a.width) pic.width = a.width;
        if (a.height) pic.height = a.height;
        return ctx.sync().then(function () { return "Gambar disisipkan dari " + a.url; });
      });
    }).catch(function (e) { return "ERROR sisip gambar: " + (e && e.message ? e.message : e); });
  };
  handlers.list_styles = function () {
    return Promise.resolve("Style bawaan: Normal, Heading1, Heading2, Heading3, Heading4, Title, Subtitle, Quote, IntenseQuote, ListParagraph, NoSpacing, TOCHeading");
  };
  // ask_user ditangani khusus di agent loop (perlu interaksi UI). Handler ini fallback.
  handlers.ask_user = function (a) {
    return Promise.resolve("PERTANYAAN ke pengguna: " + a.question + " (rekomendasi: " + a.recommendation + ")");
  };

  // ---- Dispatch satu tool call ----
  function execute(name, args) {
    var h = handlers[name];
    if (!h) return Promise.resolve("ERROR: tool '" + name + "' tidak dikenal.");
    return withLock(function () { return h(args || {}); })
      .catch(function (e) { return "ERROR menjalankan " + name + ": " + (e && e.message ? e.message : e); });
  }

  return { definitions: definitions, execute: execute };
})();
