/*
 * equation.js — LaTeX -> OMML (Office Math Markup Language).
 * Menghasilkan persamaan Word ASLI (bukan teks) via Word.body/range.insertOoxml().
 * Di-port dari deepseek-word-addin (TypeScript) ke vanilla JS.
 */
window.EQ = (function () {
  "use strict";

  function escapeXml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
  }

  var LATEX_SYMBOLS = {
    "\\alpha":"\u03b1","\\beta":"\u03b2","\\gamma":"\u03b3","\\delta":"\u03b4",
    "\\epsilon":"\u03b5","\\varepsilon":"\u03b5","\\zeta":"\u03b6","\\eta":"\u03b7",
    "\\theta":"\u03b8","\\vartheta":"\u03d1","\\iota":"\u03b9","\\kappa":"\u03ba",
    "\\lambda":"\u03bb","\\mu":"\u03bc","\\nu":"\u03bd","\\xi":"\u03be",
    "\\pi":"\u03c0","\\varpi":"\u03d6","\\rho":"\u03c1","\\sigma":"\u03c3",
    "\\tau":"\u03c4","\\upsilon":"\u03c5","\\phi":"\u03c6","\\varphi":"\u03c6",
    "\\chi":"\u03c7","\\psi":"\u03c8","\\omega":"\u03c9",
    "\\Gamma":"\u0393","\\Delta":"\u0394","\\Theta":"\u0398","\\Lambda":"\u039b",
    "\\Xi":"\u039e","\\Pi":"\u03a0","\\Sigma":"\u03a3","\\Upsilon":"\u03a5",
    "\\Phi":"\u03a6","\\Psi":"\u03a8","\\Omega":"\u03a9",
    "\\times":"\u00d7","\\div":"\u00f7","\\pm":"\u00b1","\\mp":"\u2213",
    "\\cdot":"\u00b7","\\ast":"\u2217","\\star":"\u22c6",
    "\\leq":"\u2264","\\le":"\u2264","\\geq":"\u2265","\\ge":"\u2265",
    "\\neq":"\u2260","\\ne":"\u2260","\\approx":"\u2248","\\equiv":"\u2261",
    "\\sim":"\u223c","\\propto":"\u221d","\\ll":"\u226a","\\gg":"\u226b",
    "\\sum":"\u2211","\\prod":"\u220f","\\int":"\u222b","\\oint":"\u222e",
    "\\bigcap":"\u2229","\\bigcup":"\u222a",
    "\\partial":"\u2202","\\infty":"\u221e","\\nabla":"\u2207",
    "\\forall":"\u2200","\\exists":"\u2203",
    "\\in":"\u2208","\\notin":"\u2209","\\subset":"\u2282","\\supset":"\u2283",
    "\\cup":"\u222a","\\cap":"\u2229","\\emptyset":"\u2205",
    "\\cdots":"\u22ef","\\ldots":"\u2026","\\vdots":"\u22ee",
    "\\to":"\u2192","\\rightarrow":"\u2192","\\leftarrow":"\u2190",
    "\\Rightarrow":"\u21d2","\\Leftarrow":"\u21d0","\\Leftrightarrow":"\u21d4",
    "\\langle":"\u27e8","\\rangle":"\u27e9",
    "\\lfloor":"\u230a","\\rfloor":"\u230b","\\lceil":"\u2308","\\rceil":"\u2309",
    "\\mid":"|","\\prime":"\u2032","\\circ":"\u2218","\\bullet":"\u2022",
    "\\oplus":"\u2295","\\otimes":"\u2297",
    "\\because":"\u2235","\\therefore":"\u2234",
    "\\angle":"\u2220","\\perp":"\u22a5","\\parallel":"\u2225","\\not":"\u00ac",
    "\\%":"%","\\$":"$","\\#":"#",
    "\\,":"","\\;":"","\\:":"","\\!":"","\\ ":" "
  };

  var PASSTHROUGH_CMDS = {};
  ["\\mathrm","\\mathbf","\\mathit","\\mathbb","\\mathcal","\\mathsf","\\mathtt",
   "\\text","\\textrm","\\textbf","\\textit",
   "\\hat","\\bar","\\vec","\\dot","\\ddot","\\tilde",
   "\\widehat","\\widetilde","\\overline","\\underline",
   "\\overbrace","\\underbrace","\\boldsymbol","\\operatorname"
  ].forEach(function(c){ PASSTHROUGH_CMDS[c]=1; });

  // ---- Tokenizer ----
  function tokenizeLaTeX(src) {
    var toks = [], i = 0;
    while (i < src.length) {
      var ch = src[i];
      if (ch === "\\") {
        var j = i + 1;
        if (j < src.length && /[a-zA-Z]/.test(src[j])) {
          while (j < src.length && /[a-zA-Z]/.test(src[j])) j++;
          toks.push({ t: "cmd", v: src.slice(i, j) });
        } else if (j < src.length) {
          toks.push({ t: "cmd", v: src.slice(i, j + 1) });
          j++;
        }
        i = j;
      } else if (ch === "{") { toks.push({ t: "lbrace" }); i++; }
      else if (ch === "}") { toks.push({ t: "rbrace" }); i++; }
      else if (ch === "[") { toks.push({ t: "lbracket" }); i++; }
      else if (ch === "]") { toks.push({ t: "rbracket" }); i++; }
      else if (ch === "^") { toks.push({ t: "sup" }); i++; }
      else if (ch === "_") { toks.push({ t: "sub" }); i++; }
      else if (ch === " " || ch === "\t" || ch === "\n") { i++; }
      else {
        var k = i;
        while (k < src.length && "\\{}[]^_ \t\n".indexOf(src[k]) === -1) k++;
        if (k > i) toks.push({ t: "text", v: src.slice(i, k) });
        i = k;
      }
    }
    return toks;
  }

  // ---- Parser: LaTeX tokens -> OMML ----
  function OmmlParser(toks) { this.toks = toks; this.pos = 0; }
  OmmlParser.prototype.cur = function () { return this.toks[this.pos]; };
  OmmlParser.prototype.run = function (text) {
    return '<m:r><m:t xml:space="preserve">' + escapeXml(text) + "</m:t></m:r>";
  };
  OmmlParser.prototype.parseAtom = function () {
    var tok = this.cur();
    if (!tok) return "";
    if (tok.t === "lbrace") {
      this.pos++;
      var inner = this.parseSequence(true);
      if (this.cur() && this.cur().t === "rbrace") this.pos++;
      return inner;
    }
    if (tok.t === "lbracket") { this.pos++; return this.run("["); }
    if (tok.t === "rbracket") { this.pos++; return this.run("]"); }
    if (tok.t === "text") { this.pos++; return this.run(tok.v); }
    if (tok.t === "cmd") {
      this.pos++;
      var cmd = tok.v;
      if (cmd === "\\frac" || cmd === "\\dfrac") {
        var num = this.parseAtom();
        var den = this.parseAtom();
        return '<m:f><m:fPr><m:type m:val="bar"/></m:fPr><m:num>' + num + "</m:num><m:den>" + den + "</m:den></m:f>";
      }
      if (cmd === "\\sqrt") {
        if (this.cur() && this.cur().t === "lbracket") {
          this.pos++;
          while (this.pos < this.toks.length && this.cur() && this.cur().t !== "rbracket") this.pos++;
          if (this.cur() && this.cur().t === "rbracket") this.pos++;
        }
        var arg = this.parseAtom();
        return '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>' + arg + "</m:e></m:rad>";
      }
      if (PASSTHROUGH_CMDS[cmd]) return this.parseAtom();
      if (cmd === "\\left" || cmd === "\\right") return "";
      var sym = LATEX_SYMBOLS[cmd];
      if (sym !== undefined) return sym ? this.run(sym) : "";
      return this.run(cmd.slice(1));
    }
    this.pos++;
    return "";
  };
  OmmlParser.prototype.parseNode = function () {
    var base = this.parseAtom();
    var sub = null, sup = null;
    while (true) {
      var tok = this.cur();
      if (tok && tok.t === "sub" && sub === null) { this.pos++; sub = this.parseAtom(); }
      else if (tok && tok.t === "sup" && sup === null) { this.pos++; sup = this.parseAtom(); }
      else break;
    }
    if (sub !== null && sup !== null)
      return "<m:sSubSup><m:sSubSupPr/><m:e>" + base + "</m:e><m:sub>" + sub + "</m:sub><m:sup>" + sup + "</m:sup></m:sSubSup>";
    if (sub !== null)
      return "<m:sSub><m:sSubPr/><m:e>" + base + "</m:e><m:sub>" + sub + "</m:sub></m:sSub>";
    if (sup !== null)
      return "<m:sSup><m:sSupPr/><m:e>" + base + "</m:e><m:sup>" + sup + "</m:sup></m:sSup>";
    return base;
  };
  OmmlParser.prototype.parseSequence = function (insideGroup) {
    var parts = [];
    while (this.pos < this.toks.length) {
      if (insideGroup && this.cur() && this.cur().t === "rbrace") break;
      parts.push(this.parseNode());
    }
    return parts.join("");
  };

  // ---- Bungkus OMML jadi flat-OPC package (format yang andal diterima insertOoxml) ----
  function buildEquationOoxml(latex, displayMode) {
    var omml = new OmmlParser(tokenizeLaTeX(latex)).parseSequence();
    var m = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"';
    var para = displayMode
      ? '<w:p><m:oMathPara ' + m + '><m:oMath>' + omml + '</m:oMath></m:oMathPara></w:p>'
      : '<w:p><m:oMath ' + m + '>' + omml + '</m:oMath></w:p>';
    return (
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">' +
      '<pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml" pkg:padding="512">' +
      '<pkg:xmlData><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
      '</Relationships></pkg:xmlData></pkg:part>' +
      '<pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">' +
      '<pkg:xmlData><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' + m + '>' +
      '<w:body>' + para + '<w:sectPr/></w:body></w:document></pkg:xmlData></pkg:part></pkg:package>'
    );
  }

  // ---- Deteksi rumus dalam teks markdown ----
  // Mendukung: $$...$$ (display), \[...\] (display), $...$ (inline), \(...\) (inline)
  // Mengembalikan array segmen: {type:'text'|'eq', value, display}
  function splitMathSegments(text) {
    var segs = [];
    var re = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$([^\$\n]+?)\$/g;
    var last = 0, m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) segs.push({ type: "text", value: text.slice(last, m.index) });
      if (m[1] !== undefined) segs.push({ type: "eq", value: m[1].trim(), display: true });
      else if (m[2] !== undefined) segs.push({ type: "eq", value: m[2].trim(), display: true });
      else if (m[3] !== undefined) segs.push({ type: "eq", value: m[3].trim(), display: false });
      else if (m[4] !== undefined) segs.push({ type: "eq", value: m[4].trim(), display: false });
      last = re.lastIndex;
    }
    if (last < text.length) segs.push({ type: "text", value: text.slice(last) });
    return segs;
  }

  function hasMath(text) {
    return /\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^\$\n]+?\$/.test(text);
  }

  return {
    buildEquationOoxml: buildEquationOoxml,
    splitMathSegments: splitMathSegments,
    hasMath: hasMath,
    latexToOmml: function (latex) { return new OmmlParser(tokenizeLaTeX(latex)).parseSequence(); }
  };
})();
