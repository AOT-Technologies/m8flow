const fs = require('fs');
const path = require('path');

const filePath = path.join(
  __dirname,
  '..',
  'node_modules',
  'bpmn-js-spiffworkflow',
  'app',
  'spiffworkflow',
  'extensions',
  'propertiesPanel',
  'ExtensionsPropertiesProvider.jsx'
);

const replacements = [
  {
    from: "translate('Spiffworkflow Service Properties')",
    to: "translate('M8flow Service Properties')",
  },
];

if (!fs.existsSync(filePath)) {
  console.warn('[patch-bpmn-labels] File not found, skipping:', filePath);
  process.exit(0);
}

let content = fs.readFileSync(filePath, 'utf8');
let patched = false;

for (const { from, to } of replacements) {
  if (content.includes(from)) {
    content = content.replace(from, to);
    patched = true;
  }
}

if (patched) {
  fs.writeFileSync(filePath, content, 'utf8');
  console.log('[patch-bpmn-labels] Patched bpmn-js-spiffworkflow labels successfully.');
} else {
  console.log('[patch-bpmn-labels] No changes needed (already patched or label not found).');
}
