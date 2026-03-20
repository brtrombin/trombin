const MONTHS_PT_SHORT = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
const MONTHS_PT_LONG  = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"];

module.exports = function(eleventyConfig) {

  // ── Passthrough ──────────────────────────────────────────────────────────
  eleventyConfig.addPassthroughCopy("img");
  eleventyConfig.addPassthroughCopy("CNAME");

  // ── Filters ──────────────────────────────────────────────────────────────

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

  // chunk array into arrays of N
  eleventyConfig.addFilter("chunk", (arr, size) => {
    const chunks = [];
    for (let i = 0; i < arr.length; i += size) {
      chunks.push(arr.slice(i, i + size));
    }
    return chunks;
  });

  // ── Collections ──────────────────────────────────────────────────────────

  eleventyConfig.addCollection("articles", function(collection) {
    // sort descending: most recent first
    const articles = collection.getFilteredByTag("articles")
      .filter(a => !a.data.draft)
      .sort((a, b) => b.date - a.date);

    const colors = ["c1","c2","c3","c4","c5","c6","c7","c8"];

    articles.forEach((article, i) => {
      // 001 = mais antigo, N = mais recente
      article.data.frameNumber = String(articles.length - i).padStart(3, "0");
      article.data.colorClass  = colors[i % 8];
      // prev = older article, next = more recent article
      article.data.prevArticle = articles[i + 1] || null;
      article.data.nextArticle = articles[i - 1] || null;
    });

    return articles;
  });

  // ── Config ───────────────────────────────────────────────────────────────

  // siteBase: "" localmente, "/trombin" no GitHub Pages (via env var)
  const pathPrefix = process.env.ELEVENTY_PATH_PREFIX || "/";
  const siteBase   = pathPrefix.replace(/\/$/, ""); // remove trailing slash
  eleventyConfig.addGlobalData("siteBase", siteBase);

  return {
    pathPrefix,
    templateFormats: ["njk", "md"],
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
    dir: {
      input: ".",
      output: "_site",
      includes: "_includes",
      layouts: "_includes",
    },
  };
};
