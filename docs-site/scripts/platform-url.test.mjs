import test from 'node:test';
import assert from 'node:assert/strict';
import { platformUrl } from '../src/lib/platform-url.ts';

test('本机开发与静态预览进入同一主机的应用端口', () => {
  assert.equal(platformUrl('127.0.0.1'), 'http://127.0.0.1:3000');
  assert.equal(platformUrl('localhost'), 'http://localhost:3000');
  assert.equal(platformUrl('[::1]'), 'http://[::1]:3000');
});

test('线上默认进入同域应用，独立部署使用构建时的平台地址', () => {
  assert.equal(platformUrl('crew.example.com'), '/');
  assert.equal(
    platformUrl('manual.example.com', 'https://crew.example.com/work/'),
    'https://crew.example.com/work/',
  );
  assert.equal(platformUrl('localhost', 'https://crew.example.com/'), 'https://crew.example.com/');
  assert.equal(platformUrl('crew.example.com', '  '), '/');
});
