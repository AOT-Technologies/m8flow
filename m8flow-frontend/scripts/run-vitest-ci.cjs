const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const rootDir = path.resolve(__dirname, '..');
const srcDir = path.join(rootDir, 'src');
const vitestEntrypoint = path.join(rootDir, 'node_modules', 'vitest', 'vitest.mjs');
const isWindows = process.platform === 'win32';

function collectTestFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const entryPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      files.push(...collectTestFiles(entryPath));
      continue;
    }

    if (/\.test\.tsx?$/.test(entry.name)) {
      files.push(path.relative(rootDir, entryPath).replace(/\\/g, '/'));
    }
  }

  return files;
}

const testFiles = collectTestFiles(srcDir).sort();

const groupDefinitions = [
  {
    name: 'template-modeler',
    match: (file) => file === 'src/views/TemplateModelerPage.test.tsx',
  },
  {
    name: 'tenant-dialogs',
    match: (file) =>
      /^src\/views\/Tenant(ManagementPage|Page|RoleDialog|SelectPage)\.test\.tsx$/.test(file),
  },
  {
    name: 'tenant-login',
    match: (file) => /^src\/views\/TenantAwareLogin\.test\.tsx$/.test(file),
  },
  {
    name: 'app-root',
    match: (file) => file === 'src/App.test.tsx',
  },
  {
    name: 'container-extensions',
    match: (file) => file === 'src/ContainerForExtensions.test.tsx',
  },
  {
    name: 'tenant-services',
    match: (file) =>
      /^src\/services\/(TenantService|UserService)\.test\.ts$/.test(file),
  },
  {
    name: 'template-pages-and-service',
    match: (file) =>
      /^src\/views\/Template(?!ModelerPage).*\.test\.tsx?$/.test(file) ||
      /^src\/components\/SaveAsTemplateModal\.test\.tsx$/.test(file) ||
      /^src\/hooks\/useTemplates\.test\.ts$/.test(file) ||
      /^src\/services\/TemplateService\.test\.ts$/.test(file),
  },
  {
    name: 'template-cards-and-utils',
    match: (file) =>
      /^src\/test\/Template.*\.test\.tsx$/.test(file) ||
      /^src\/test\/templateHelpers\.test\.ts$/.test(file) ||
      /^src\/utils\/template.*\.test\.ts$/.test(file),
  },
  {
    name: 'remaining',
    match: () => true,
  },
];

const groups = groupDefinitions.map(({ name }) => ({ name, files: [] }));

for (const file of testFiles) {
  const groupIndex = groupDefinitions.findIndex(({ match }) => match(file));
  if (groupIndex === -1) {
    throw new Error(`No CI test shard matched ${file}`);
  }
  groups[groupIndex].files.push(file);
}

const assignedFiles = groups.flatMap((group) => group.files);
if (assignedFiles.length !== testFiles.length) {
  throw new Error('CI test sharding did not cover every test file exactly once.');
}

function chunkFiles(files, size) {
  if (!size || size <= 0 || files.length <= size) {
    return [files];
  }

  const batches = [];
  for (let index = 0; index < files.length; index += size) {
    batches.push(files.slice(index, index + size));
  }
  return batches;
}

function getBatchSizeForGroup(groupName) {
  if (!isWindows) {
    return null;
  }

  if (groupName === 'template-cards-and-utils') {
    return 1;
  }

  return null;
}

for (const group of groups) {
  if (group.files.length === 0) {
    continue;
  }

  const batches = chunkFiles(group.files, getBatchSizeForGroup(group.name));

  for (const [batchIndex, batchFiles] of batches.entries()) {
    const batchLabel =
      batches.length > 1
        ? ` [batch ${batchIndex + 1}/${batches.length}]`
        : '';
    console.log(
      `\n=== Running Vitest shard: ${group.name}${batchLabel} (${batchFiles.length} files) ===`,
    );
    const result = spawnSync(
      process.execPath,
      [vitestEntrypoint, 'run', ...batchFiles],
      {
        cwd: rootDir,
        env: process.env,
        stdio: 'inherit',
      },
    );

    if (result.status !== 0) {
      process.exit(result.status ?? 1);
    }
  }
}
