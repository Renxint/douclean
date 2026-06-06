/**
 * 抖音 API 签名服务 - Puppeteer 浏览器代理
 *
 * bdms SDK 自动劫持 XHR/fetch 注入 a_bogus。
 * 本服务充当透明代理：Python 发来 URL，浏览器代发请求，返回响应。
 *
 * 启动: npm start    端口: 8765
 */

const express = require('express');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

const app = express();
app.use(express.json());
const PORT = process.env.PORT || 8765;

let browser, page;
let ready = false;
let initError = null;

async function launchBrowser() {
  console.log('[Browser] Launching...');
  browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled'],
  });
  page = await browser.newPage();

  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
  });
  await page.setViewport({ width: 1920, height: 1080 });
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36'
  );

  console.log('[Browser] Loading douyin (fresh cookies)...');
  await page.goto('https://www.douyin.com/?recommend=1', {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
  await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));
  console.log('[Browser] Ready!');
  ready = true;
}

// ============ API ============

app.get('/health', (req, res) => {
  res.json({ status: ready ? 'ok' : 'initializing', ready, error: initError });
});

/**
 * POST /set_cookies - 注入登录 Cookie 到浏览器
 */
app.post('/set_cookies', async (req, res) => {
  if (!ready) return res.status(503).json({ error: 'Not ready' });
  const { cookie_string } = req.body;
  if (!cookie_string) return res.status(400).json({ error: 'Missing cookie_string' });

  try {
    const cookies = cookie_string.split(';').map(c => {
      const eq = c.trim().indexOf('=');
      if (eq < 0) return null;
      return {
        name: c.substring(0, eq).trim(),
        value: c.substring(eq + 1).trim(),
        domain: '.douyin.com',
        path: '/',
      };
    }).filter(Boolean);

    // 先导航到 douyin 让页面自然加载
    await page.goto('https://www.douyin.com/?recommend=1', {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });

    // 再注入 Cookie（页面加载后注入，不会被覆盖）
    await page.setCookie(...cookies);
    console.log(`[Cookie] Injected ${cookies.length} cookies`);

    // 重新初始化 SDK (Cookie 已就位)
    await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
    await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));
    console.log('[Cookie] SDK re-initialized with cookies');

    // 同时注入指纹到 localStorage (翻页必需)
    const { webid, verifyFp, fp, uifid } = req.body;
    if (webid || verifyFp || fp || uifid) {
      await page.evaluate((vals) => {
        if (vals.webid) localStorage.setItem('webid', vals.webid);
        if (vals.verifyFp) localStorage.setItem('verifyFp', vals.verifyFp);
        if (vals.fp) localStorage.setItem('fp', vals.fp);
        if (vals.uifid) localStorage.setItem('uifid', vals.uifid);
      }, { webid, verifyFp, fp, uifid });
      console.log('[Fingerprint] Injected');
    }

    res.json({ ok: true, count: cookies.length });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * GET /sign - 仅提取签名参数 (a_bogus + msToken)
 * Python 用这个获取签名，然后用 requests 直发请求
 */
app.get('/sign', async (req, res) => {
  if (!ready) return res.status(503).json({ error: 'Not ready' });
  const { url } = req.query;
  if (!url) return res.status(400).json({ error: 'Missing "url"' });

  try {
    // 通过 CDP 网络拦截捕获签名后的请求
    const cdpSession = await page.createCDPSession();
    await cdpSession.send('Network.enable');

    const signedPromise = new Promise((resolve) => {
      const timeout = setTimeout(() => resolve(null), 5000);

      cdpSession.on('Network.requestWillBeSent', (params) => {
        const reqUrl = params.request.url;
        if (reqUrl.includes('aweme/v1/web/aweme/post')) {
          clearTimeout(timeout);
          resolve(reqUrl);
        }
      });

      // 触发 fetch (bdms SDK 会拦截并签名)
      page.evaluate((targetUrl) => {
        fetch(targetUrl, { credentials: 'include' }).catch(() => {});
      }, url);
    });

    const capturedUrl = await signedPromise;
    await cdpSession.detach();

    let result = { a_bogus: '', msToken: '', full_url: url };

    if (capturedUrl) {
      try {
        const parsed = new URL(capturedUrl);
        result.a_bogus = parsed.searchParams.get('a_bogus') || '';
        result.msToken = parsed.searchParams.get('msToken') || '';
        result.full_url = capturedUrl;
      } catch (e) { /* keep defaults */ }
    }

    // 补 msToken
    if (!result.msToken) {
      result.msToken = await page.evaluate(() => localStorage.getItem('xmst') || '');
    }

    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /fetch - 浏览器代发请求
 */
app.post('/fetch', async (req, res) => {
  if (!ready) return res.status(503).json({ error: 'Not ready' });

  const { url, method = 'GET', headers = {}, body } = req.body;
  if (!url) return res.status(400).json({ error: 'Missing "url"' });

  try {
    const result = await page.evaluate(async ({ url, method, headers, body }) => {
      const opts = { method, headers: { ...headers }, credentials: 'include' };
      if (body) opts.body = body;
      const resp = await fetch(url, opts);
      const text = await resp.text();
      let data;
      try { data = JSON.parse(text); } catch (e) { data = text; }
      return {
        status: resp.status,
        statusText: resp.statusText,
        responseHeaders: Object.fromEntries(resp.headers.entries()),
        data,
      };
    }, { url, method, headers: JSON.parse(JSON.stringify(headers)), body });

    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /scroll_user - 模拟滚动用户主页获取全部作品 (无需手动翻页)
 */
app.post('/scroll_user', async (req, res) => {
  if (!ready) return res.status(503).json({ error: 'Not ready' });
  const { sec_user_id, max_scrolls = 50 } = req.body;
  if (!sec_user_id) return res.status(400).json({ error: 'Missing sec_user_id' });

  try {
    const allPosts = [];
    const seenIds = new Set();

    const responseHandler = async (response) => {
      const rurl = response.url();
      if (rurl.includes('aweme/v1/web/aweme/post')) {
        try {
          const data = await response.json();
          if (data && data.aweme_list) {
            for (const a of data.aweme_list) {
              if (!seenIds.has(a.aweme_id)) {
                seenIds.add(a.aweme_id);
                allPosts.push(a);
              }
            }
          }
        } catch (e) { /* not JSON */ }
      }
    };
    // 先注册拦截再导航 (避免漏掉初始请求)
    page.on('response', responseHandler);

    // 打开用户主页
    const userUrl = `https://www.douyin.com/user/${sec_user_id}`;
    console.log(`[Scroll] Loading ${userUrl}`);
    await page.goto(userUrl, { waitUntil: 'networkidle2', timeout: 90000 });
    await new Promise(r => setTimeout(r, 4000));

    let prev = allPosts.length, stuck = 0;
    console.log(`[Scroll] Initial: ${allPosts.length}`);

    for (let i = 0; i < max_scrolls; i++) {
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await new Promise(r => setTimeout(r, 5000));
      console.log(`[Scroll] #${i + 1}: ${allPosts.length}`);
      if (allPosts.length === prev) { stuck++; if (stuck >= 5) break; }
      else { stuck = 0; prev = allPosts.length; }
    }

    page.off('response', responseHandler);
    console.log(`[Scroll] Done: ${allPosts.length} posts`);

    // 恢复首页 (以便 /fetch 能正常工作)
    await page.goto('https://www.douyin.com/?recommend=1', {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });
    await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
    await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));

    res.json({ count: allPosts.length, aweme_list: allPosts });
  } catch (err) {
    console.error('[Scroll] Error:', err.message);
    try {
      await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
      await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));
    } catch (e) { }
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /fetch_on_user_page - 导航到用户主页后在页面内发 API 请求
 */
app.post('/fetch_on_user_page', async (req, res) => {
  if (!ready) return res.status(503).json({ error: 'Not ready' });
  const { sec_user_id, api_url } = req.body;
  if (!sec_user_id || !api_url) return res.status(400).json({ error: 'Missing params' });

  try {
    // 导航到用户主页
    await page.goto(`https://www.douyin.com/user/${sec_user_id}`, {
      waitUntil: 'domcontentloaded', timeout: 60000,
    });
    await new Promise(r => setTimeout(r, 3000));

    // 在用户页面内发 API 请求
    const result = await page.evaluate(async (targetUrl) => {
      const resp = await fetch(targetUrl, { credentials: 'include' });
      const text = await resp.text();
      let data;
      try { data = JSON.parse(text); } catch (e) { data = text; }
      return { status: resp.status, data };
    }, api_url);

    // 恢复首页
    await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
    await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));

    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 调试: 抓取用户页面的所有 API 请求 URL
app.get('/debug/capture', async (req, res) => {
  if (!ready) return res.status(503).json({ error: 'Not ready' });
  const sec_id = req.query.sec_user_id;
  if (!sec_id) return res.status(400).json({ error: 'Missing sec_user_id' });

  try {
    const capturedUrls = [];
    const cdp = await page.createCDPSession();
    await cdp.send('Network.enable');

    cdp.on('Network.requestWillBeSent', (params) => {
      const u = params.request.url;
      if (u.includes('aweme/v1/web/aweme/post')) {
        capturedUrls.push(u);
        console.log('[Capture]', u.substring(0, 200));
      }
    });

    await page.goto(`https://www.douyin.com/user/${sec_id}`, {
      waitUntil: 'domcontentloaded', timeout: 60000,
    });
    await new Promise(r => setTimeout(r, 3000));

    // 滚动几次
    for (let i = 0; i < 10; i++) {
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await new Promise(r => setTimeout(r, 3000));
    }

    await cdp.detach();

    // 恢复首页
    await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
    await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));

    res.json({ count: capturedUrls.length, urls: capturedUrls });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 调试
app.get('/debug/state', async (req, res) => {
  if (!page) return res.status(503).json({ error: 'Not ready' });
  const info = await page.evaluate(() => ({
    url: window.location.href,
    bdms: window.bdms ? Object.keys(window.bdms) : null,
    xmst: (localStorage.getItem('xmst') || '').substring(0, 40) + '...',
    // 浏览器指纹
    webid: localStorage.getItem('webid') || '',
    verifyFp: localStorage.getItem('verifyFp') || '',
    fp: localStorage.getItem('fp') || '',
    cookies: document.cookie.substring(0, 200),
  }));
  res.json(info);
});

// ============ 启动 ============
(async () => {
  try { await launchBrowser(); }
  catch (err) { initError = err.message; console.error('[FATAL]', err.message); }

  app.listen(PORT, () => {
    console.log(`\n=== 抖音 API 代理服务 ===`);
    console.log(`http://localhost:${PORT}`);
    console.log(`POST /fetch       - 浏览器代发请求`);
    console.log(`POST /scroll_user - 滚动主页获取全部作品`);
    console.log(`GET  /health      - 健康检查`);
  });
})();
