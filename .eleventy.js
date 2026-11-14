// Configuração do Eleventy (gerador do site).
//
// Define: arquivos copiados sem processamento, filtros usados nos templates
// (.njk), a collection "articles" e as pastas de entrada/saída.
// Build: npm run build → gera _site/   |   Dev: npm run serve

const MONTHS_PT_SHORT = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
const MONTHS_PT_LONG  = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"];

module.exports = function(eleventyConfig) {

  // ── Passthrough ──────────────────────────────────────────────────────────
  // Copiados para _site/ como estão. CNAME = domínio próprio no GitHub Pages.
  eleventyConfig.addPassthroughCopy("img");
  eleventyConfig.addPassthroughCopy("CNAME");

  // ── Filters ──────────────────────────────────────────────────────────────
  // Uso nos templates: {{ valor | nomeDoFiltro }}.
  // As datas usam getUTC*: o Eleventy lê "date: 2025-02-10" como meia-noite
  // UTC, e no fuso do Brasil a versão local cairia no dia anterior.

  // "fev 2025"
  eleventyConfig.addFilter("dateFormattedPT", (date) => {
    const d = new Date(date);
    return `${MONTHS_PT_SHORT[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  });

  // "fevereiro 2025"
  eleventyConfig.addFilter("dateLong", (date) => {
    const d = new Date(date);
    return `${MONTHS_PT_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  });

  // "2025 02 10"
  eleventyConfig.addFilter("dateStamp", (date) => {
    const d = new Date(date);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, "0");
    const day = String(d.getUTCDate()).padStart(2, "0");
    return `${y} ${m} ${day}`;
  });

  // "POA RS" — tudo antes do " · " no campo location
  eleventyConfig.addFilter("locShort", (loc) => {
    if (!loc) return "";
    return loc.split(" · ")[0];
  });

  // "2025 02" — ano e mês do dateStamp
  eleventyConfig.addFilter("dateYM", (date) => {
    const d = new Date(date);
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, "0");
    return `${y} ${m}`;
  });

  // temas únicos de todos os artigos, ordenados alfabeticamente
  eleventyConfig.addFilter("uniqueThemes", (articles) => {
    const seen = new Set();
    for (const a of (articles || [])) {
      for (const t of (a.data.themes || [])) seen.add(t);
    }
    return [...seen].sort((a, b) => a.localeCompare(b, "pt"));
  });

  // divide um array em grupos de N itens — usado na home para montar
  // as tiras de 4 frames: [a,b,c,d,e] | chunk(4) → [[a,b,c,d],[e]]
  eleventyConfig.addFilter("chunk", (arr, size) => {
    const chunks = [];
    for (let i = 0; i < arr.length; i += size) {
      chunks.push(arr.slice(i, i + size));
    }
    return chunks;
  });

  // descarta os N primeiros itens
  eleventyConfig.addFilter("skip", (arr, n) => (arr || []).slice(n));

  // ── Collections ──────────────────────────────────────────────────────────

  // "articles" = todos os .md de /articles (a tag vem de articles/articles.json),
  // menos os rascunhos (draft: true). Além de ordenar, grava em cada artigo
  // dados que os templates usam: frameNumber, colorClass, prevArticle, nextArticle.
  eleventyConfig.addCollection("articles", function(collection) {
    // ordem decrescente: mais recente primeiro
    const articles = collection.getFilteredByTag("articles")
      .filter(a => !a.data.draft)
      .sort((a, b) => b.date - a.date);

    // classes de degradê (definidas no CSS da home) para frames sem foto
    const colors = ["c1","c2","c3","c4","c5","c6","c7","c8"];

    articles.forEach((article, i) => {
      // 001 = mais antigo, N = mais recente
      article.data.frameNumber = String(articles.length - i).padStart(3, "0");
      article.data.colorClass  = colors[i % 8];
      // prev = texto mais antigo, next = texto mais recente
      article.data.prevArticle = articles[i + 1] || null;
      article.data.nextArticle = articles[i - 1] || null;
    });

    return articles;
  });

  // ── Config ───────────────────────────────────────────────────────────────

  // siteBase: "" localmente, "/trombin" no GitHub Pages (via env var)
  const pathPrefix = process.env.ELEVENTY_PATH_PREFIX || "/";
  const siteBase   = pathPrefix.replace(/\/$/, ""); // remove a barra final
  eleventyConfig.addGlobalData("siteBase", siteBase);

  return {
    pathPrefix,                      // base do filtro | url nos templates
    templateFormats: ["njk", "md"],
    markdownTemplateEngine: "njk",   // permite {{ }} e {% %} dentro dos .md
    htmlTemplateEngine: "njk",
    dir: {
      input: ".",
      output: "_site",
      includes: "_includes",         // nav.njk
      layouts: "_includes",          // article.njk, ensaio.njk
    },
  };
};
