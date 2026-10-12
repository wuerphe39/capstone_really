// Export the same overall SVG shown by the interactive HTML for GitHub README.
// No browser or extra package is needed: only the diagram's data and renderer run.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const htmlPath = path.join(root, 'docs', 'PetMind_실장비_블록도.html');
const svgPath = path.join(root, 'docs', 'PetMind_전체_블록도.svg');
const html = fs.readFileSync(htmlPath, 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
if (!script) throw new Error('Architecture diagram script not found');

const boundary = script.indexOf('let current=');
const palette = script.match(/^const palette=.*;$/m)?.[0];
const escapeHtml = script.match(/^const esc=.*;$/m)?.[0];
if (boundary < 0 || !palette || !escapeHtml) {
  throw new Error('Architecture diagram renderer changed; review the exporter');
}

const svg = vm.runInNewContext(
  `${script.slice(0, boundary)}\n${palette}\n${escapeHtml}\nsystemSvg()`,
  {}, { timeout: 1000 },
);
if (!svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"') || !svg.endsWith('</svg>')) {
  throw new Error('Architecture diagram did not render an SVG');
}
// The HTML emphasizes one route at a time; show every route in the static image.
const standalone = svg.replace('<svg ',
  '<svg style="font-family:Malgun Gothic,Apple SD Gothic Neo,sans-serif" ')
  .replaceAll('opacity=".16"', 'opacity=".48"');
fs.writeFileSync(svgPath, `${standalone.replace(/></g, '>\n<')}\n`, 'utf8');
console.log(path.relative(root, svgPath));
