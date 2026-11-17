import { mkdir, mkdtemp, readdir, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';

// Bundle repository TSX only. Dependencies stay external, sharing one React instance.
const root = resolve('.');
await mkdir(join(root, 'node_modules/.cache'), { recursive: true });
const directory = await mkdtemp(join(root, 'node_modules/.cache/pricing-dom-'));
try {
  const entries = (await readdir(join(root, 'tests'))).filter(name => name.endsWith('.test.jsx'));
  await build({ entryPoints: entries.map(name => join(root, 'tests', name)), outdir: directory,
    outExtension: { '.js': '.mjs' }, bundle: true, packages: 'external', platform: 'node',
    format: 'esm', jsx: 'automatic', loader: { '.css': 'empty' }, logLevel: 'warning' });
  const files = entries.map(name => join(directory, name.replace(/\.jsx$/, '.mjs')));
  const result = spawnSync(process.execPath, ['--import', pathToFileURL(join(root, 'tests/dom-setup.mjs')).href,
    '--test', '--test-concurrency=1', ...files], { cwd: root, stdio: 'inherit', timeout: 120000 });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally {
  await rm(directory, { recursive: true, force: true });
}
