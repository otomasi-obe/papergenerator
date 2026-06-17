/*
 * markdown.js — Konversi Markdown -> HTML yang aman untuk Office.js insertHtml.
 * Pakai `marked` bila tersedia (di-load via CDN di taskpane.html); jika gagal,
 * fallback ke konverter ringan bawaan. Output HTML dirancang agar Word
 * merender heading, tabel, list, bold/italic, dan blockquote sebagai format asli.
 */
window.MD = (function () {
  "use strict";

  // ---- Konverter fallback ringan (tanpa dependensi) ----
  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function inline(s) {
    // escape dulu, lalu terapkan bold/italic/code
    s = escapeHtml(s);
    s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
    s = s.replace(/(^|[^*])\*([^*]+)\*/g, "$1<i>$2</i>");
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
    return s;
  }

  function fallbackConvert(md) {
    var lines = md.replace(/\r\n/g, "\n").split("\n");
    var html = [];
    var i = 0;
    var listOpen = null; // 'ul' | 'ol'

    function closeList() {
      if (listOpen) { html.push("</" + listOpen + ">"); listOpen = null; }
    }

    while (i < lines.length) {
      var line = lines[i];

      // Tabel markdown (header | --- | rows)
      if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
        closeList();
        var headerCells = line.split("|").slice(1, -1).map(function (c) { return c.trim(); });
        var t = ['<table border="1" style="border-collapse:collapse">'];
        t.push("<tr>" + headerCells.map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") + "</tr>");
        i += 2; // lewati baris pemisah
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
          var cells = lines[i].split("|").slice(1, -1).map(function (c) { return c.trim(); });
          t.push("<tr>" + cells.map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>");
          i++;
        }
        t.push("</table>");
        html.push(t.join(""));
        continue;
      }

      // Heading
      var h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        closeList();
        var lvl = h[1].length;
        html.push("<h" + lvl + ">" + inline(h[2]) + "</h" + lvl + ">");
        i++; continue;
      }

      // Horizontal rule
      if (/^\s*---+\s*$/.test(line)) {
        closeList();
        html.push("<hr/>");
        i++; continue;
      }

      // Blockquote
      if (/^\s*>\s?/.test(line)) {
        closeList();
        html.push("<blockquote>" + inline(line.replace(/^\s*>\s?/, "")) + "</blockquote>");
        i++; continue;
      }

      // Unordered list
      if (/^\s*[-*+]\s+/.test(line)) {
        if (listOpen !== "ul") { closeList(); html.push("<ul>"); listOpen = "ul"; }
        html.push("<li>" + inline(line.replace(/^\s*[-*+]\s+/, "")) + "</li>");
        i++; continue;
      }

      // Ordered list
      if (/^\s*\d+\.\s+/.test(line)) {
        if (listOpen !== "ol") { closeList(); html.push("<ol>"); listOpen = "ol"; }
        html.push("<li>" + inline(line.replace(/^\s*\d+\.\s+/, "")) + "</li>");
        i++; continue;
      }

      // Baris kosong
      if (/^\s*$/.test(line)) {
        closeList();
        i++; continue;
      }

      // Paragraf biasa
      closeList();
      html.push("<p>" + inline(line) + "</p>");
      i++;
    }
    closeList();
    return html.join("");
  }

  // ---- API utama ----
  function toHtml(md) {
    if (!md) return "";
    if (window.marked) {
      try {
        if (typeof window.marked.parse === "function") return window.marked.parse(md);
        if (typeof window.marked === "function") return window.marked(md);
      } catch (e) { /* fallback */ }
    }
    return fallbackConvert(md);
  }

  return { toHtml: toHtml };
})();
