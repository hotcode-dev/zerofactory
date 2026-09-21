/**
 * Zero Factory dashboard CSS build.
 *
 * Regenerates dashboard/dist/style.css from dashboard/input.css using the
 * Tailwind CSS v4 compiler. The output is a *scoped* stylesheet:
 *   - every Tailwind utility used by dashboard/dist/index.js is emitted,
 *   - the Zero Factory custom keyframes / helpers (zfk-*) are hoisted to the
 *     top level (so `animation: zfk-pulse` resolves),
 *   - the theme + utility rules are wrapped in `@scope (.zerofactory-root)`
 *     so they cannot leak into / be overridden by the host Hermes UI.
 *
 * Portability:
 *   - input.css imports Tailwind as a BARE package path ("tailwindcss/...").
 *     This script resolves that package relative to the project (walking up
 *     from the repo root looking for node_modules/tailwindcss) or honours the
 *     ZEROFACTORY_TAILWIND_DIR env override. No machine-specific absolute
 *     paths are hard-coded anywhere, so `node dashboard/build_css.mjs`
 *     succeeds on a fresh clone once `npm install` has been run.
 *
 * Candidate extraction:
 *   Tailwind v4's JS `compile().build(candidates)` API does not auto-scan the
 *   `@source` file (only the CLI does), so we extract the class tokens that
 *   dist/index.js actually uses and hand them to the compiler explicitly.
 *   Every `className` literal in index.js is a static string (no template
 *   interpolation), so a static token scan is complete.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const inputPath = path.join(__dirname, 'input.css');
const sourceJsPath = path.join(__dirname, 'dist', 'index.js');
const outputPath = path.join(__dirname, 'dist', 'style.css');

/**
 * Resolve the installed tailwindcss package directory.
 *
 * Order:
 *   1. $ZEROFACTORY_TAILWIND_DIR  (may point at node_modules/ or the pkg dir)
 *   2. node_modules/tailwindcss found by walking up from this file
 * Throws a helpful error if neither exists so a fresh clone fails fast instead
 * of silently producing a broken stylesheet.
 */
function resolveTailwindRoot() {
  const isPkgDir = (dir) => {
    try {
      const pj = path.join(dir, 'package.json');
      if (!fs.existsSync(pj)) return false;
      return JSON.parse(fs.readFileSync(pj, 'utf8')).name === 'tailwindcss';
    } catch (_) {
      return false;
    }
  };

  if (process.env.ZEROFACTORY_TAILWIND_DIR) {
    const d = path.resolve(process.env.ZEROFACTORY_TAILWIND_DIR);
    if (isPkgDir(d)) return d;
    if (isPkgDir(path.join(d, 'tailwindcss'))) return path.join(d, 'tailwindcss');
    throw new Error(
      `ZEROFACTORY_TAILWIND_DIR is set to ${d} but tailwindcss was not found there.`,
    );
  }

  let cur = __dirname;
  for (let i = 0; i < 8; i++) {
    const cand = path.join(cur, 'node_modules', 'tailwindcss');
    if (fs.existsSync(path.join(cand, 'package.json'))) return cand;
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  throw new Error(
    'Cannot locate the tailwindcss package. Run `npm install` at the repository ' +
      'root (or set ZEROFACTORY_TAILWIND_DIR to a node_modules directory that ' +
      'contains tailwindcss) and then re-run `node dashboard/build_css.mjs`.',
  );
}

/**
 * Extract the utility/variant class tokens that dist/index.js actually uses.
 * Scans every double-, single-, and backtick-quoted string for whitespace
 * separated tokens that look like Tailwind candidates (letters/digits and the
 * chars Tailwind allows in a class: _ : . / % # ! [ ]). This is what feeds the
 * v4 compiler so it only emits rules the UI references (and — crucially — the
 * variant-prefixed rules such as hover:bg-slate-800 and disabled:opacity-40).
 */
function extractCandidates(source) {
  const candidates = new Set();
  const tokenRe = /^[A-Za-z0-9_:\[\]/%#!. -]+$/; // conservative charset
  for (const m of source.matchAll(/"([^"]*)"|'([^']*)'|`([^`]*)`/g)) {
    const s = m[1] ?? m[2] ?? m[3] ?? '';
    for (const raw of s.split(/\s+/)) {
      const tok = raw.trim();
      if (!tok || tok.length < 2) continue;
      if (tok.startsWith('//')) continue; // skip URLs
      if (!tokenRe.test(tok)) continue;
      if (!/[a-z]/.test(tok)) continue; // skip pure-numeric / symbol noise
      candidates.add(tok);
    }
  }
  return [...candidates];
}

// ---- 1. Locate the Tailwind package and load its JS API -------------------
const twBase = resolveTailwindRoot();
console.log(`Using tailwindcss from ${twBase}`);
const tw = await import(path.join(twBase, 'dist', 'lib.mjs'));

// ---- 2. Rewrite bare package imports to absolute file paths --------------
let input = fs.readFileSync(inputPath, 'utf8');
input = input.replace(
  /@import\s+["']tailwindcss\/(theme|utilities|preflight|index)\.css["']/g,
  (_m, f) => `@import "${path.join(twBase, `${f}.css`)}"`,
);

// ---- 3. Compile ---------------------------------------------------------
const compiler = await tw.compile(input, {
  base: __dirname,
  loadStylesheet: async (id, fromBase) => {
    const p = path.isAbsolute(id) ? id : path.resolve(fromBase || __dirname, id);
    return { path: p, base: path.dirname(p), content: fs.readFileSync(p, 'utf8') };
  },
});

const candidates = extractCandidates(fs.readFileSync(sourceJsPath, 'utf8'));
console.log(`Extracted ${candidates.length} candidate class tokens from dist/index.js`);

const raw = compiler.build(candidates);

// ---- 4. Hoist @keyframes to the top level -------------------------------
// The Zero Factory custom animations (zfk-pulse, zfk-spin) must sit OUTSIDE the
// @scope wrapper so `animation: zfk-pulse` inside the scope resolves. Hoist any
// top-level @keyframes block that appears after the layer/theme preamble.
const keyframes = [];
const body = raw.replace(/@keyframes\s+([A-Za-z0-9_-]+)\s*\{[\s\S]*?\n\}/g, (match) => {
  keyframes.push(match);
  return '';
});

// ---- 5. Scope the theme + utilities -------------------------------------
const scopedBody = body.replace(/:root,?\s*:host/g, ':scope, .zerofactory-root').trim();

const scopedCss = `/*! Zero Factory Scoped Stylesheet - Tailwind CSS v4 */
${keyframes.map((k) => k.trimEnd()).join('\n\n')}

@scope (.zerofactory-root) {
${scopedBody}
}
`;

fs.writeFileSync(outputPath, scopedCss);
console.log(`Successfully generated scoped CSS at ${outputPath} (${scopedCss.length} bytes, ${keyframes.length} keyframes hoisted)`);
