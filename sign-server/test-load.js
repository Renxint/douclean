/**
 * SDK 加载测试 - 使用 Object.defineProperty 绕过 Node 24 的 getter 限制
 */
const fs = require('fs');
const path = require('path');
const { patchGlobalEnvironment } = require('./env-patch');

const sdkDir = path.join(__dirname, 'sdk');
console.log('=== 抖音 SDK 加载测试 (defineProperty 注入) ===\n');

// 注入环境到 global (用 defineProperty 避免 getter 冲突)
const win = patchGlobalEnvironment();
const inject = {
  window: win, self: win, globalThis: win,
  navigator: win.navigator, document: win.document,
  location: win.location, localStorage: win.localStorage,
  sessionStorage: win.sessionStorage, performance: win.performance,
  screen: win.screen, XMLHttpRequest: win.XMLHttpRequest,
  fetch: win.fetch,
  Request: win.Request, Response: win.Response, Headers: win.Headers,
  URL: win.URL, URLSearchParams: win.URLSearchParams,
  Blob: win.Blob, TextEncoder: win.TextEncoder, TextDecoder: win.TextDecoder,
  crypto: win.crypto,
  addEventListener: win.addEventListener, removeEventListener: win.removeEventListener,
  dispatchEvent: win.dispatchEvent, CustomEvent: win.CustomEvent, Event: win.Event,
};

for (const [key, val] of Object.entries(inject)) {
  try {
    Object.defineProperty(global, key, {
      value: val, writable: true, configurable: true, enumerable: true,
    });
  } catch (e) {
    // 一些 key 在 strict 模式下可能无法重新定义，忽略
    console.log(`  [warn] Cannot inject: ${key} (${e.message})`);
  }
}

const sdks = [
  { name: 'webmssdk', file: 'webmssdk.es5.js' },
  { name: 'secsdk', file: 'runtime_bundler_34_v2.js' },
  { name: 'bdms', file: 'bdms.js' },
];

for (const sdk of sdks) {
  const filepath = path.join(sdkDir, sdk.file);
  const code = fs.readFileSync(filepath, 'utf-8');
  process.stdout.write(`[${sdk.name}] ${code.length} chars... `);

  try {
    eval(code);
    console.log('OK');
  } catch (err) {
    console.log('FAIL');
    console.error(`  Error: ${err.message}`);
    if (err.stack) {
      const stack = err.stack.split('\n');
      stack.slice(0, 4).forEach(l => console.error('  ', l.trim().substring(0, 150)));
    }
    process.exit(1);
  }
}

console.log('\n=== All SDKs loaded ===');
const bdms = win.bdms;
console.log('bdms type:', typeof bdms);
if (bdms) {
  const allKeys = Object.keys(bdms);
  console.log('bdms keys:', allKeys);
  console.log('  functions:', allKeys.filter(k => typeof bdms[k] === 'function'));
}
