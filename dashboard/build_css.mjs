import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const inputPath = path.join(__dirname, 'input.css');
const outputPath = path.join(__dirname, 'dist', 'style.css');
const tmpRaw = path.join(__dirname, 'dist', '.raw_style.css');

// 1. Compile Tailwind CSS
console.log('Compiling Tailwind CSS with @tailwindcss/cli...');
execSync(`npx -y @tailwindcss/cli -i "${inputPath}" -o "${tmpRaw}"`, { stdio: 'inherit' });

let raw = fs.readFileSync(tmpRaw, 'utf8');
try { fs.unlinkSync(tmpRaw); } catch (_) {}

// 2. Extract keyframes to top-level
const keyframes = [];
raw = raw.replace(/@keyframes[\s\S]*?\n}\n}/g, (m) => {
  keyframes.push(m);
  return '';
});
raw = raw.replace(/@keyframes[\s\S]*?\n}/g, (m) => {
  keyframes.push(m);
  return '';
});

// 3. Replace global root/host selectors with scoped selector
raw = raw.replace(/:root,\s*:host/g, ':scope, .zerofactory-kanban-root');

// 4. Wrap everything in @scope (.zerofactory-kanban-root)
const scopedCss = `/*! Zero Factory Kanban Scoped Stylesheet - Tailwind CSS v4 */
${keyframes.join('\n\n')}

@scope (.zerofactory-kanban-root) {
${raw.trim()}
}
`;

fs.writeFileSync(outputPath, scopedCss);
console.log(`Successfully generated scoped CSS at ${outputPath} (${scopedCss.length} bytes)`);
