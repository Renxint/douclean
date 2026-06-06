/**
 * 抖音签名补环境 - 浏览器环境模拟
 * 模拟 bdms / secsdk / webmssdk 需要的浏览器 API
 */

function patchGlobalEnvironment() {
  const now = Date.now();

  // ============ Navigator ============
  const navigator = {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    platform: 'Win32',
    language: 'zh-CN',
    languages: ['zh-CN', 'zh'],
    hardwareConcurrency: 32,
    deviceMemory: 8,
    maxTouchPoints: 0,
    vendor: 'Google Inc.',
    vendorSub: '',
    productSub: '20030107',
    cookieEnabled: true,
    onLine: true,
    webdriver: false,
    appName: 'Netscape',
    appVersion: '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    plugins: { length: 5, item: () => null, namedItem: () => null, refresh: () => {} },
    mimeTypes: { length: 4, item: () => null, namedItem: () => null },
    connection: {
      effectiveType: '4g',
      rtt: 50,
      downlink: 10,
      saveData: false,
      type: 'cellular',
    },
    getBattery: () => Promise.resolve({ charging: true, level: 1, chargingTime: 0, dischargingTime: Infinity }),
    sendBeacon: () => true,
    mediaDevices: { enumerateDevices: () => Promise.resolve([]) },
    permissions: { query: () => Promise.resolve({ state: 'prompt' }) },
    serviceWorker: undefined,
    geolocation: undefined,
    getGamepads: () => [],
    canPlayType: () => 'probably',
    requestMediaKeySystemAccess: () => Promise.reject(),
  };

  // ============ Screen ============
  const screen = {
    width: 2560,
    height: 1440,
    availWidth: 2560,
    availHeight: 1400,
    colorDepth: 24,
    pixelDepth: 24,
    availLeft: 0,
    availTop: 0,
  };

  // ============ Performance ============
  const performance = {
    now: () => performance.now._base + (Date.now() - performance.startTime),
    now: Object.assign(function() { return Date.now() - performance.startTime + performance.now._base; }, {
      _base: 138000.5,
    }),
    timing: {
      navigationStart: now - 2500,
      unloadEventStart: 0,
      unloadEventEnd: 0,
      redirectStart: 0,
      redirectEnd: 0,
      fetchStart: now - 2000,
      domainLookupStart: now - 1900,
      domainLookupEnd: now - 1850,
      connectStart: now - 1850,
      connectEnd: now - 1700,
      secureConnectionStart: now - 1750,
      requestStart: now - 1650,
      responseStart: now - 800,
      responseEnd: now - 500,
      domLoading: now - 400,
      domInteractive: now - 200,
      domContentLoadedEventStart: now - 100,
      domContentLoadedEventEnd: now - 50,
      domComplete: 0,
      loadEventStart: 0,
      loadEventEnd: 0,
    },
    getEntriesByType: () => [],
    getEntriesByName: () => [],
    mark: () => {},
    measure: () => {},
    memory: { totalJSHeapSize: 45000000, usedJSHeapSize: 35000000, jsHeapSizeLimit: 2190000000 },
    timeOrigin: now - 2500,
  };
  performance.startTime = now;

  // ============ localStorage / sessionStorage ============
  const storageData = {};
  const localStorage = {
    getItem: (k) => storageData[k] || null,
    setItem: (k, v) => { storageData[k] = String(v); },
    removeItem: (k) => { delete storageData[k]; },
    clear: () => { Object.keys(storageData).forEach(k => delete storageData[k]); },
    get length() { return Object.keys(storageData).length; },
    key: (i) => Object.keys(storageData)[i] || null,
  };
  // Simulate existing msToken
  localStorage.setItem('xmst', generateMsToken());

  const sessionStorage = {
    _data: {},
    getItem: (k) => sessionStorage._data[k] || null,
    setItem: (k, v) => { sessionStorage._data[k] = String(v); },
    removeItem: (k) => { delete sessionStorage._data[k]; },
    clear: () => { sessionStorage._data = {}; },
    length: 0,
    key: () => null,
  };

  // ============ Document (minimal) ============
  const document = {
    cookie: '',
    referrer: 'https://www.douyin.com/',
    title: '抖音-记录美好生活',
    domain: 'www.douyin.com',
    URL: 'https://www.douyin.com/',
    documentElement: {
      getAttribute: () => null,
      style: {},
    },
    createElement: (tag) => {
      const el = {
        tagName: tag.toUpperCase(),
        style: {},
        setAttribute: () => {},
        getAttribute: () => null,
        appendChild: () => {},
        removeChild: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        innerHTML: '',
        src: '',
        nonce: '',
        onload: null,
        onerror: null,
      };
      if (tag === 'canvas') {
        el.getContext = (type) => {
          if (type === '2d') {
            return {
              fillText: () => {},
              measureText: () => ({ width: 120 }),
              fillRect: () => {},
              clearRect: () => {},
              getImageData: () => ({ data: new Uint8Array(100) }),
              putImageData: () => {},
              save: () => {},
              restore: () => {},
              scale: () => {},
              rotate: () => {},
              translate: () => {},
              transform: () => {},
              setTransform: () => {},
              beginPath: () => {},
              closePath: () => {},
              moveTo: () => {},
              lineTo: () => {},
              stroke: () => {},
              fill: () => {},
              arc: () => {},
              rect: () => {},
              font: '',
              textAlign: 'start',
              textBaseline: 'alphabetic',
              fillStyle: '',
              strokeStyle: '',
              lineWidth: 1,
              globalAlpha: 1,
              globalCompositeOperation: 'source-over',
            };
          }
          if (type === 'webgl' || type === 'experimental-webgl') {
            return {
              getParameter: (p) => {
                if (p === 37445) return 'WebGL Rendering Engine';
                if (p === 37446) return 'WebKit WebGL';
                if (p === 7937) return 'Intel Inc.';
                if (p === 7938) return 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)';
                return null;
              },
              getExtension: () => null,
              getSupportedExtensions: () => [],
            };
          }
          return null;
        };
        el.toDataURL = () => 'data:image/png;base64,';
      }
      return el;
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: () => null,
    getElementsByTagName: () => [],
    getElementsByClassName: () => [],
    head: { appendChild: () => {} },
    body: { appendChild: () => {}, style: {} },
    addEventListener: () => {},
    removeEventListener: () => {},
    createEvent: () => ({ initEvent: () => {} }),
  };

  // ============ Location ============
  const location = {
    href: 'https://www.douyin.com/?recommend=1',
    origin: 'https://www.douyin.com',
    protocol: 'https:',
    host: 'www.douyin.com',
    hostname: 'www.douyin.com',
    port: '',
    pathname: '/',
    search: '?recommend=1',
    hash: '',
    assign: () => {},
    replace: () => {},
    reload: () => {},
  };

  // ============ XMLHttpRequest ============
  const XMLHttpRequest = function() {
    this.readyState = 0;
    this.status = 0;
    this.responseText = '';
    this.response = null;
    this.responseType = '';
    this.onreadystatechange = null;
    this.onload = null;
    this.onerror = null;
    this.upload = { onprogress: null };
    this.withCredentials = false;
    this._requestHeaders = {};
    this.setRequestHeader = (k, v) => { this._requestHeaders[k] = v; };
    this.getResponseHeader = () => null;
    this.getAllResponseHeaders = () => '';
    this.overrideMimeType = () => {};
    this.open = (method, url, async) => {
      this.readyState = 1;
      if (this.onreadystatechange) this.onreadystatechange();
    };
    this.send = () => {
      this.readyState = 4;
      this.status = 200;
      this.responseText = '{}';
      if (this.onreadystatechange) this.onreadystatechange();
      if (this.onload) this.onload();
    };
    this.abort = () => {};
  };

  // ============ Web APIs (Fetch family) ============
  const Request = globalThis.Request || function Request(input, init) {
    this.url = typeof input === 'string' ? input : input.url;
    this.method = (init && init.method) || 'GET';
    this.headers = new Headers(init && init.headers);
    this.body = init && init.body;
    this.signal = init && init.signal;
  };
  const Response = globalThis.Response || function Response(body, init) {
    this.body = body;
    this.status = (init && init.status) || 200;
    this.statusText = (init && init.statusText) || 'OK';
    this.headers = new Headers(init && init.headers);
    this.ok = this.status >= 200 && this.status < 300;
    this.json = () => Promise.resolve(JSON.parse(typeof body === 'string' ? body : '{}'));
    this.text = () => Promise.resolve(typeof body === 'string' ? body : '');
  };
  const Headers = globalThis.Headers || function Headers(init) {
    this._headers = {};
    if (init) {
      if (init instanceof Headers) {
        init = init._headers;
      }
      Object.entries(init || {}).forEach(([k, v]) => { this._headers[k.toLowerCase()] = String(v); });
    }
    this.append = (k, v) => { this._headers[k.toLowerCase()] = String(v); };
    this.set = (k, v) => { this._headers[k.toLowerCase()] = String(v); };
    this.get = (k) => this._headers[k.toLowerCase()] || null;
    this.has = (k) => k.toLowerCase() in this._headers;
    this.delete = (k) => { delete this._headers[k.toLowerCase()]; };
    this.forEach = (fn) => { Object.entries(this._headers).forEach(([k, v]) => fn(v, k, this)); };
  };
  const URL = globalThis.URL || function URL(url, base) {
    this.href = url;
    this.origin = '';
    this.protocol = 'https:';
    this.host = '';
    this.hostname = '';
    this.pathname = '';
    this.search = '';
    this.hash = '';
  };
  const URLSearchParams = globalThis.URLSearchParams || function URLSearchParams(init) {
    this.append = () => {};
    this.set = () => {};
    this.get = () => null;
    this.toString = () => '';
  };
  const Blob = globalThis.Blob || function Blob(parts, options) {
    this.size = 0;
    this.type = (options && options.type) || '';
    this.text = () => Promise.resolve('');
  };
  const TextEncoder = globalThis.TextEncoder || function TextEncoder() {
    this.encode = (s) => Buffer.from(s, 'utf-8');
  };
  const TextDecoder = globalThis.TextDecoder || function TextDecoder() {
    this.decode = (buf) => Buffer.from(buf).toString('utf-8');
  };
  const crypto = globalThis.crypto || {
    getRandomValues: (arr) => { for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256); return arr; },
    subtle: {
      digest: () => Promise.resolve(new Uint8Array(32)),
      importKey: () => Promise.resolve({}),
      encrypt: () => Promise.resolve(new Uint8Array(32)),
      decrypt: () => Promise.resolve(new Uint8Array(32)),
    },
    randomUUID: () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16); }),
  };
  const Intl = globalThis.Intl || {};

  // ============ Fetch (will be intercepted by secsdk) ============
  let originalFetch = globalThis.fetch || global.fetch || (() => Promise.resolve(new Response('{}', { status: 200 })));

  // ============ Other globals ============
  const console = {
    log: (...args) => { /* suppress */ },
    warn: (...args) => { /* suppress */ },
    error: (...args) => { /* suppress */ },
    info: (...args) => { /* suppress */ },
    debug: (...args) => { /* suppress */ },
  };

  // ============ Construct window/self/globalThis ============
  const _window = {
    navigator,
    screen,
    performance,
    localStorage,
    sessionStorage,
    document,
    location,
    XMLHttpRequest,
    fetch: originalFetch,
    console,
    // 基础方法
    setTimeout: globalThis.setTimeout,
    setInterval: globalThis.setInterval,
    clearTimeout: globalThis.clearTimeout,
    clearInterval: globalThis.clearInterval,
    Request,
    Response,
    Headers,
    URL,
    URLSearchParams,
    Blob,
    TextEncoder,
    TextDecoder,
    crypto,
    Intl,
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
    // 事件系统
    addEventListener: (name, fn) => { (_window._listeners[name] = _window._listeners[name] || []).push(fn); },
    removeEventListener: (name, fn) => { if (_window._listeners[name]) _window._listeners[name] = _window._listeners[name].filter(f => f !== fn); },
    dispatchEvent: (event) => { const fns = _window._listeners[event.type] || []; fns.forEach(fn => fn(event)); return true; },
    _listeners: {},
    CustomEvent: function(type, opts) { this.type = type; this.detail = (opts && opts.detail) || null; },
    Event: function(type) { this.type = type; },
    // 常用属性
    innerWidth: 2560,
    innerHeight: 1440,
    outerWidth: 2560,
    outerHeight: 1440,
    devicePixelRatio: 1,
    name: '',
    closed: false,
    opener: null,
    parent: null,
    top: null,
    frames: [],
    length: 0,
    __ac_referer: '',
    __ac_nonce: '',
    // 存储原始 fetch 给 secsdk
    _request: originalFetch,
    // SdkGlueInit 占位 - 后续由 sdk-glue 覆盖
    _SdkGlueInit: null,
    // 网页标记函数
    mark: () => {},
    // 存储空间
    globalThis: undefined,
    self: undefined,
  };

  // 循环引用
  _window.globalThis = _window;
  _window.self = _window;
  _window.window = _window;

  return _window;
}

function generateMsToken() {
  // msToken 是 128 字符的 hex-like 随机串
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  let result = '';
  for (let i = 0; i < 128; i++) {
    result += chars[Math.floor(Math.random() * chars.length)];
  }
  return result;
}

module.exports = { patchGlobalEnvironment, generateMsToken };
