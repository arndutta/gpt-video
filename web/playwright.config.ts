import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';

export default defineConfig({
  testDir: './browser-tests',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: '../data/browser-qa/artifacts',
  reporter: [['list'], ['json', { outputFile: '../data/browser-qa/results.json' }]],
  use: { baseURL: 'http://127.0.0.1:5173', viewport: { width: 1280, height: 900 },
    browserName: 'chromium', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: {
    command: `"${python}" -m scripts.browser_fixture`, cwd: root,
    url: 'http://127.0.0.1:5173/__qa/ready', timeout: 60_000,
    reuseExistingServer: false,
  },
});
