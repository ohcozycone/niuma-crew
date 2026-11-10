import { watch } from 'node:fs';
import { buildDesignExamples } from './build-design-examples.mjs';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { repoRoot, siteRoot, syncContent } from './sync-content.mjs';

await syncContent();
await buildDesignExamples();
const require = createRequire(import.meta.url);
const child = spawn(
  process.execPath,
  [
    require.resolve('next/dist/bin/next'),
    'dev',
    '--webpack',
    '--hostname',
    '127.0.0.1',
    '--port',
    '3001',
  ],
  { cwd: siteRoot, stdio: 'inherit' },
);
let timer;
let pending = Promise.resolve();
let examplesChanged = false;
function schedule(examples = false) {
  examplesChanged ||= examples;
  clearTimeout(timer);
  timer = setTimeout(() => {
    const rebuildExamples = examplesChanged;
    examplesChanged = false;
    pending = pending
      .then(async () => {
        await syncContent();
        if (rebuildExamples) await buildDesignExamples();
      })
      .catch((error) => {
        console.error('文档同步失败：', error.message);
      });
  }, 350);
}
const extensions = new Set([
  '.md',
  '.mdx',
  '.svg',
  '.png',
  '.jpg',
  '.jpeg',
  '.webp',
  '.gif',
  '.pdf',
]);
const sourceExtensions = new Set(['.ts', '.tsx', '.css', '.json']);
const watchers = [
  'docs',
  'backend/app',
  'frontend/src',
  'frontend/public/brand',
  'frontend/public/failures',
].map((dir) =>
  watch(path.join(repoRoot, dir), { recursive: true }, (_event, filename) => {
    if (!filename) return;
    const extension = path.extname(filename);
    if (!extensions.has(extension) && !(dir === 'frontend/src' && sourceExtensions.has(extension)))
      return;
    schedule(dir.startsWith('frontend/') && extension !== '.md');
  }),
);
watchers.push(
  watch(repoRoot, (_event, filename) => {
    if (filename === 'README.md') schedule();
  }),
);

function close(signal = 'SIGTERM') {
  clearTimeout(timer);
  for (const watcher of watchers) watcher.close();
  child.kill(signal);
}
process.on('SIGINT', () => close('SIGINT'));
process.on('SIGTERM', () => close());
child.on('exit', (code) => {
  close();
  process.exitCode = code ?? 1;
});
