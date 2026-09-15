#!/usr/bin/env node
/**
 * BEST Express Vietnam Tracker via Playwright Bot Bypass
 *
 * Bypasses bot detection using rebrowser-playwright + headed Chrome,
 * intercepts the expresslistinfo API response, and extracts tracking events.
 *
 * Usage:
 *   node scripts/fetch_best_playwright.mjs <TRACKING_CODE> [--proxy <PROXY_URL>] [--session <SESSION_JSON>]
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const args = process.argv.slice(2);
let trackingCode = null;
let proxyUrl = null;
let sessionPath = path.join(os.homedir(), '.best_express_session.json');

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--proxy' && args[i + 1]) {
    proxyUrl = args[++i];
  } else if (args[i] === '--session' && args[i + 1]) {
    sessionPath = args[++i];
  } else if (!trackingCode && !args[i].startsWith('--')) {
    trackingCode = args[i].trim();
  }
}

if (!trackingCode) {
  console.error('Usage: node scripts/fetch_best_playwright.mjs <TRACKING_CODE> [--proxy <PROXY_URL>]');
  process.exit(1);
}

// Dynamically resolve playwright-bot-bypass
const skillTemplate = 'C:\\Users\\hozkg\\.agents\\skills\\playwright-bot-bypass\\scripts\\stealth-template.mjs';
const { createStealthBrowser } = await import(`file:///${skillTemplate.replace(/\\/g, '/')}`);

console.log(`=======================================================`);
console.log(`  BEST Express Live Tracker (Playwright Stealth)`);
console.log(`  Code: ${trackingCode}`);
if (proxyUrl) console.log(`  Proxy: ${proxyUrl}`);
console.log(`=======================================================\n`);

const options = {
  headless: false, // Required for headed Chrome & stealth
  viewport: { width: 1280, height: 850 },
};

if (proxyUrl) {
  options.proxy = { server: proxyUrl };
}

if (fs.existsSync(sessionPath)) {
  try {
    options.storageState = sessionPath;
    console.log(`[Session] Reusing saved session from: ${sessionPath}`);
  } catch (e) {
    console.warn(`[Session] Could not load session: ${e.message}`);
  }
}

const { browser, context, page } = await createStealthBrowser(options);

let trackingResult = null;
let resolved = false;

page.on('response', async (response) => {
  const url = response.url();
  if (url.includes('/express-cc/express/expresslistinfo')) {
    try {
      const json = await response.json();
      if (json && json.success && json.data && json.data.expressList) {
        console.log('\n[API Intercept] Tracking information received successfully!');
        trackingResult = json.data.expressList;
        resolved = true;
      } else if (json && json.errorCode === 'risk_001') {
        console.log('[Notice] BEST Express triggered rotate-captcha (risk_001).');
        console.log('>>> Please slide the captcha puzzle in the browser window to continue <<<');
      }
    } catch {}
  }
});

try {
  const targetUrl = `https://www.best-inc.vn/track?bills=${encodeURIComponent(trackingCode)}`;
  console.log(`Opening: ${targetUrl}`);
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });

  console.log('Waiting for tracking data (solve captcha in browser if shown)...');

  // Poll for up to 60 seconds to allow user to slide captcha
  const startTime = Date.now();
  while (!resolved && (Date.now() - startTime < 60000)) {
    await page.waitForTimeout(1000);
  }

  if (resolved && trackingResult) {
    console.log('\n================ TRACKING RESULT ================');
    for (const item of trackingResult) {
      console.log(`Parcel: ${item.expressId} (${item.statusName || 'Unknown Status'})`);
      if (item.traces && item.traces.length > 0) {
        console.log('\nEvents (newest first):');
        for (const trace of item.traces) {
          console.log(`  - [${trace.actionTime || trace.time}] ${trace.description || trace.actionName} (${trace.siteName || trace.city || ''})`);
        }
      } else {
        console.log('  No events recorded yet.');
      }
    }

    // Save session state to avoid re-triggering captcha on next run
    try {
      await context.storageState({ path: sessionPath });
      console.log(`\n[Session] Saved valid session state to: ${sessionPath}`);
    } catch {}

    // Output JSON result file for integration
    const outPath = path.join(process.cwd(), 'data', `best_${trackingCode}.json`);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(trackingResult, null, 2), 'utf-8');
    console.log(`[Output] Detailed JSON saved to: ${outPath}`);
  } else {
    console.warn('\n[Timeout] No tracking events received within 60s. Captcha was not solved or code not found.');
  }

} catch (err) {
  console.error('[Error]', err.message);
} finally {
  await browser.close();
}
