const express = require('express');
const puppeteer = require('puppeteer');
const app = express();
app.use(express.json());
const PORT = process.env.PORT || 8765;

let browser, page, ready = false, initError = null;

async function launchBrowser() {
  browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled'],
  });
  page = await browser.newPage();
  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
  });
  await page.setViewport({ width: 1920, height: 1080 });
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36');

  // Inject login cookie
  const COOKIE_STR = 'passport_csrf_token=410b2f04ab46606b8580c373aa02ec02; passport_csrf_token_default=410b2f04ab46606b8580c373aa02ec02; sid_guard=c5a5336bb8e8656817bd932f8395ed1c%7C1760803134%7C5184000%7CWed%2C+17-Dec-2025+15%3A58%3A54+GMT; sid_ucp_v1=1.0.0-KDY1MDU3Njk3NmEzNzYzMTAzNDQzNTA1YzFhOGExZGM5N2NkYjYzOWYKGQi738efiQIQvvLOxwYY7zEgDDgGQPQHSAQaAmxmIiBjNWE1MzM2YmI4ZTg2NTY4MTdiZDkzMmY4Mzk1ZWQxYw; ssid_ucp_v1=1.0.0-KDY1MDU3Njk3NmEzNzYzMTAzNDQzNTA1YzFhOGExZGM5N2NkYjYzOWYKGQi738efiQIQvvLOxwYY7zEgDDgGQPQHSAQaAmxmIiBjNWE1MzM2YmI4ZTg2NTY4MTdiZDkzMmY4Mzk1ZWQxYw; s_v_web_id=verify_mh4qxq4c_H9xVW79H_4bal_49Oj_BTec_WSForRkJOxsW; ttwid=1%7C8PGRDLzZbyKcnddb1KK8s4lL1MTDBGpTE1Hz9c1iKME%7C1762358564%7Cecdcfbd4dc875968a4e5a97473569a3960f33f7baa39b51208ce4f797834e506; passport_auth_mix_state=b09ehxj5sy5n2g27d1ov5xw042zicvddkzdq0wgzbj53jl6j';
  const cookies = COOKIE_STR.split('; ').map(c => {
    const eq = c.indexOf('=');
    return { name: c.substring(0, eq), value: c.substring(eq + 1), domain: '.douyin.com', path: '/' };
  });
  await page.setCookie(...cookies);

  console.log('[Browser] Cookie injected, loading douyin...');
  await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'networkidle2', timeout: 90000 });
  await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
  await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));
  ready = true;
  console.log('[Browser] Ready');
}

// ---- Routes ----

app.get('/health', (req, res) => {
  res.json({ status: ready ? 'ok' : 'initializing', ready, error: initError });
});

app.post('/fetch', async (req, res) => {
  if (!ready) return res.status(503).json({ error: 'Not ready' });
  const { url, method = 'GET', headers = {}, body } = req.body;
  if (!url) return res.status(400).json({ error: 'Missing url' });
  try {
    const result = await page.evaluate(async (opts) => {
      const resp = await fetch(opts.url, { method: opts.method, headers: opts.headers, credentials: 'include', body: opts.body || undefined });
      const text = await resp.text();
      let data; try { data = JSON.parse(text); } catch (e) { data = text; }
      return { status: resp.status, responseHeaders: Object.fromEntries(resp.headers.entries()), data };
    }, { url, method, headers: JSON.parse(JSON.stringify(headers)), body });
    res.json(result);
  } catch (err) { res.status(500).json({ error: err.message }); }
});

app.post('/scroll_user', async (req, res) => {
  if (!ready) return res.status(503).json({ error: 'Not ready' });
  const { sec_user_id, max_scrolls = 50 } = req.body;
  if (!sec_user_id) return res.status(400).json({ error: 'Missing sec_user_id' });

  try {
    // Use page.on('response') to intercept ALL network responses at CDP level
    const allPosts = [];
    const seenIds = new Set();

    const responseHandler = async (response) => {
      const url = response.url();
      if (url.includes('aweme/v1/web/aweme/post')) {
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
        } catch (e) { /* not JSON or streamed */ }
      }
    };
    page.on('response', responseHandler);

    // Navigate to user page
    const userUrl = `https://www.douyin.com/user/${sec_user_id}`;
    console.log(`[Scroll] Loading ${userUrl}`);
    await page.goto(userUrl, { waitUntil: 'networkidle2', timeout: 60000 });
    await new Promise(r => setTimeout(r, 2000));

    let prev = allPosts.length, stuck = 0;
    console.log(`[Scroll] Initial: ${allPosts.length}`);

    for (let i = 0; i < max_scrolls; i++) {
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await new Promise(r => setTimeout(r, 3000));
      console.log(`[Scroll] #${i + 1}: ${allPosts.length}`);
      if (allPosts.length === prev) { stuck++; if (stuck >= 3) break; }
      else { stuck = 0; prev = allPosts.length; }
    }

    page.off('response', responseHandler);
    console.log(`[Scroll] Done: ${allPosts.length} posts`);

    // Restore homepage
    await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
    await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));

    res.json({ count: allPosts.length, aweme_list: allPosts });
  } catch (err) {
    console.error('[Scroll] Error:', err.message);
    try {
      await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'networkidle2', timeout: 30000 });
      await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
      await page.evaluate(() => window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }));
    } catch (e) { }
    res.status(500).json({ error: err.message });
  }
});

app.get('/debug/state', async (req, res) => {
  if (!page) return res.status(503).json({ error: 'Not ready' });
  const info = await page.evaluate(() => ({
    url: window.location.href,
    bdms: window.bdms ? Object.keys(window.bdms) : null,
    xmst: (localStorage.getItem('xmst') || '').substring(0, 30),
  }));
  res.json(info);
});

(async () => {
  try { await launchBrowser(); } catch (err) { initError = err.message; }
  app.listen(PORT, () => console.log(`Sign server: http://localhost:${PORT}`));
})();
