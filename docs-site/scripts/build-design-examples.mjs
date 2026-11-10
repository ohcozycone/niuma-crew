import { spawn } from 'node:child_process';
import { cp } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export async function buildDesignExamples() {
  const frontendRoot = fileURLToPath(new URL('../../frontend/', import.meta.url));
  const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
  // Vite 构建会设置 NODE_ENV；独立进程避免污染随后启动的 Next 开发服务。
  await new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        path.join(path.dirname(require.resolve('vite/package.json')), 'bin/vite.js'),
        'build',
        '--config',
        fileURLToPath(new URL('../../frontend/vite.docs.config.ts', import.meta.url)),
      ],
      { cwd: frontendRoot, stdio: 'inherit', env: { ...process.env, NODE_ENV: 'production' } },
    );
    child.once('error', reject);
    child.once('exit', (code) =>
      code === 0 ? resolve() : reject(new Error(`设计示例构建失败：${code}`)),
    );
  });
  await cp(
    new URL('../../frontend/public/failures/', import.meta.url),
    new URL('../public/failures/', import.meta.url),
    { recursive: true },
  );
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url)
  await buildDesignExamples();
