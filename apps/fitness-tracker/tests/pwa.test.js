import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');

function walk(dir) {
  return readdirSync(new URL(dir, root), { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? walk(`${dir}${entry.name}/`) : [`${dir}${entry.name}`],
  );
}

test('the service worker caches every file the app needs offline, and nothing missing', () => {
  const listed = [...read('sw.js').matchAll(/^\s+'([^']+)',$/gm)].map((m) => m[1]);
  const files = [...walk('src/'), ...walk('icons/'), 'index.html', 'styles.css', 'manifest.webmanifest'];
  assert.deepEqual(
    files.filter((f) => !listed.includes(f)),
    [],
    'files the service worker does not cache',
  );
  assert.deepEqual(
    listed.filter((f) => f !== './' && !files.includes(f)),
    [],
    'cached paths that do not exist',
  );
});

test('the manifest makes the app installable', () => {
  const manifest = JSON.parse(read('manifest.webmanifest'));
  assert.equal(manifest.display, 'standalone');
  assert.ok(manifest.icons.some((i) => i.sizes === '192x192'));
  assert.ok(manifest.icons.some((i) => i.sizes === '512x512' && i.purpose === 'maskable'));
  for (const icon of manifest.icons) assert.ok(existsSync(new URL(icon.src, root)), icon.src);
});
