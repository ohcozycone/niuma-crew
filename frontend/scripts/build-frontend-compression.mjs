/** Precompress the shared SPA entry and text assets for static delivery. */
import fs from "node:fs";
import path from "node:path";
import { gzipSync, brotliCompressSync } from "node:zlib";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../dist/", import.meta.url));
function compress(directory) {
  for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
    const file = path.join(directory, item.name);
    if (item.isDirectory()) compress(file);
    else if (/\.(?:html|css|js|svg|json)$/.test(file)) {
      const source = fs.readFileSync(file);
      fs.writeFileSync(file + ".gz", gzipSync(source, { level: 9 }));
      fs.writeFileSync(file + ".br", brotliCompressSync(source));
    }
  }
}
compress(root);
