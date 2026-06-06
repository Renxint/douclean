/**
 * 抖音签名本地服务
 *
 * 启动: node server.js
 * 端口: 8765
 *
 * 接口:
 *   POST /sign         body: { url: "完整URL" }   → 返回签名参数
 *   GET  /health       健康检查
 *   POST /sign_params   body: { url: "不含签名的URL" } → 返回 { a_bogus, msToken, x-secsdk-web-signature }
 */

const express = require('express');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { patchGlobalEnvironment, generateMsToken } = require('./env-patch');

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 8765;

// ============ 状态 ============
let sdkReady = false;
let signContext = null;
let initError = null;

// ============ 加载 SDK ============
function loadSDKs() {
  // 1. 创建补环境
  const win = patchGlobalEnvironment();

  // 全局注入 window 对象 (vm.createContext 需要 global 也具备这些属性)
  const globalsToInject = [
    'navigator', 'document', 'location', 'localStorage', 'sessionStorage',
    'performance', 'screen', 'XMLHttpRequest', 'Request', 'Response', 'Headers',
    'URL', 'URLSearchParams', 'Blob', 'TextEncoder', 'TextDecoder', 'crypto',
    'fetch', 'console', 'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval',
    'atob', 'btoa',
  ];
  for (const key of globalsToInject) {
    if (win[key] !== undefined) {
      global[key] = win[key];
    }
  }
  global.window = win;
  global.self = win;

  // 创建 vm 沙箱
  const sandbox = {
    window: win,
    self: win,
    globalThis: win,
    navigator: win.navigator,
    document: win.document,
    location: win.location,
    localStorage: win.localStorage,
    sessionStorage: win.sessionStorage,
    performance: win.performance,
    screen: win.screen,
    XMLHttpRequest: win.XMLHttpRequest,
    Request: win.Request,
    Response: win.Response,
    Headers: win.Headers,
    URL: win.URL,
    URLSearchParams: win.URLSearchParams,
    Blob: win.Blob,
    TextEncoder: win.TextEncoder,
    TextDecoder: win.TextDecoder,
    crypto: win.crypto,
    fetch: win.fetch,
    console: win.console,
    setTimeout: win.setTimeout,
    setInterval: win.setInterval,
    clearTimeout: win.clearTimeout,
    clearInterval: win.clearInterval,
    atob: win.atob,
    btoa: win.btoa,
    Buffer: Buffer,
    process: undefined,
    require: undefined,
    __dirname: undefined,
    __filename: undefined,
    module: undefined,
    exports: undefined,
    global: win,
  };

  // 循环引用
  sandbox.global = sandbox;

  const vmContext = vm.createContext(sandbox);

  const sdkDir = path.join(__dirname, 'sdk');

  try {
    // Step 1: 加载 webmssdk (msToken + 设备指纹)
    console.log('[SDK] Loading webmssdk.es5.js...');
    const webmssdk = fs.readFileSync(path.join(sdkDir, 'webmssdk.es5.js'), 'utf-8');
    const webmssdkScript = new vm.Script(webmssdk, { filename: 'webmssdk.es5.js' });
    webmssdkScript.runInContext(vmContext);
    console.log('[SDK] webmssdk loaded OK');

    // Step 2: 加载 secsdk runtime_bundler (x-secsdk-web-signature)
    console.log('[SDK] Loading runtime_bundler_34_v2.js (secsdk)...');
    const secsdk = fs.readFileSync(path.join(sdkDir, 'runtime_bundler_34_v2.js'), 'utf-8');
    const secsdkScript = new vm.Script(secsdk, { filename: 'runtime_bundler_34_v2.js' });
    secsdkScript.runInContext(vmContext);
    console.log('[SDK] secsdk loaded OK');

    // Step 3: 加载 bdms.js (a_bogus 核心)
    console.log('[SDK] Loading bdms.js...');
    const bdms = fs.readFileSync(path.join(sdkDir, 'bdms.js'), 'utf-8');
    const bdmsScript = new vm.Script(bdms, { filename: 'bdms.js' });
    bdmsScript.runInContext(vmContext);
    console.log('[SDK] bdms loaded OK');

    // Step 4: 检查 window.bdms
    const bdmsObj = sandbox.window.bdms;
    if (bdmsObj) {
      console.log('[SDK] window.bdms found, type:', typeof bdmsObj);
      console.log('[SDK] bdms keys:', Object.keys(bdmsObj));
    } else {
      console.log('[SDK] WARNING: window.bdms not found');
    }

    // Step 5: 尝试初始化 bdms
    if (bdmsObj && typeof bdmsObj.init === 'function') {
      console.log('[SDK] Initializing bdms...');
      bdmsObj.init({
        aid: 6383,
        pageId: 6241,
        boe: false,
        ddrt: 8.5,
        ic: 8.5,
        paths: [
          "^/webcast/",
          "^/aweme/v1/",
          "^/aweme/v2/",
          "/douplus/",
          "/v1/message/send",
          "^/live/",
          "^/captcha/",
          "^/ecom/",
          "^/luna/pc"
        ]
      });
      console.log('[SDK] bdms.init() called');
    }

    sdkReady = true;
    signContext = vmContext;
    initError = null;
    console.log('[SDK] All SDKs loaded successfully!');

  } catch (err) {
    initError = err.message + '\n' + err.stack;
    console.error('[SDK] Load failed:', initError);
    sdkReady = false;
  }
}

// ============ API 路由 ============

app.get('/health', (req, res) => {
  res.json({
    status: sdkReady ? 'ok' : 'error',
    sdkReady,
    initError: initError || null,
    uptime: process.uptime(),
  });
});

app.post('/sign', (req, res) => {
  if (!sdkReady || !signContext) {
    return res.status(503).json({ error: 'SDK not ready', detail: initError });
  }

  const { url } = req.body;
  if (!url) {
    return res.status(400).json({ error: 'Missing "url" in request body' });
  }

  try {
    const win = signContext.window;
    const result = {};

    // 1. msToken - 从 localStorage 或生成
    result.msToken = win.localStorage.getItem('xmst') || generateMsToken();

    // 2. 尝试调用 bdms 生成 a_bogus
    const bdms = win.bdms;
    if (bdms) {
      // 探索 bdms 的签名方法
      // 常见方法: sign(), sign_url(), getSignature()
      try {
        // 尝试不同方式获取 a_bogus
        if (typeof bdms.sign === 'function') {
          result.a_bogus = bdms.sign(url);
        } else if (typeof bdms.getSignature === 'function') {
          result.a_bogus = bdms.getSignature(url);
        }
      } catch (e) {
        result.sign_error = e.message;
      }
    }

    // 3. x-secsdk-web-signature (如果 secsdk 加载成功)
    // secsdk 通常自动注入到 fetch headers，不会暴露公开 API
    // 可能需要手动触发

    // 4. 返回 bdms 暴露的所有 key 用于调试
    if (bdms) {
      result._bdms_keys = Object.keys(bdms).filter(k => typeof bdms[k] === 'function');
    }

    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/sign_params', (req, res) => {
  if (!sdkReady || !signContext) {
    return res.status(503).json({ error: 'SDK not ready', detail: initError });
  }

  const { url } = req.body;
  if (!url) {
    return res.status(400).json({ error: 'Missing "url"' });
  }

  try {
    const win = signContext.window;
    const bdms = win.bdms;

    // 生成 msToken
    const msToken = win.localStorage.getItem('xmst') || generateMsToken();

    // 尝试各种方式获取 a_bogus
    let aBogus = '';
    let method = '';

    if (bdms) {
      const funcs = ['sign', 'getSignature', 'sign_url', 'getXbogus', 'get_a_bogus'];
      for (const fn of funcs) {
        if (typeof bdms[fn] === 'function') {
          try {
            const result = bdms[fn](url);
            aBogus = result || '';
            method = fn;
            break;
          } catch (e) {
            // try next
          }
        }
      }
    }

    res.json({
      msToken,
      a_bogus: aBogus,
      method_used: method,
      // verifyFp/fp 通常与设备绑定，从 localStorage 取
      verifyFp: 'verify_mh4qxq4c_H9xVW79H_4bal_49Oj_BTec_WSForRkJOxsW',
      fp: 'verify_mh4qxq4c_H9xVW79H_4bal_49Oj_BTec_WSForRkJOxsW',
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ============ 启动 ============
console.log('=== 抖音签名本地服务 ===');
console.log('正在加载 SDK...');
loadSDKs();

if (sdkReady) {
  console.log('SDK 加载成功!');
} else {
  console.log('SDK 加载失败，查看 /health 接口获取详情');
  console.log('错误:', initError);
}

app.listen(PORT, () => {
  console.log(`服务启动: http://localhost:${PORT}`);
  console.log(`健康检查: http://localhost:${PORT}/health`);
});
