/** Capture and verify the exact check-later.md workflow in chronological order. */
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const outputDir = path.join(__dirname, 'gif-frames');
const frames = [];

async function setBanner(page, text) {
  await page.evaluate((label) => {
    document.getElementById('__tab_banner__')?.remove();
    const banner = document.createElement('div');
    banner.id = '__tab_banner__';
    banner.textContent = label;
    banner.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:48px;display:flex;align-items:center;justify-content:center;background:#b42318;color:white;font:700 18px system-ui;z-index:99999;';
    document.body.prepend(banner);
    document.body.style.paddingTop = '52px';
  }, text);
}

async function capture(page, name, label, duration = 2.5, settleTime = 200) {
  await setBanner(page, label);
  await page.bringToFront();
  await page.waitForTimeout(settleTime);
  const filename = `${String(frames.length + 1).padStart(3, '0')}-${name}.png`;
  await page.screenshot({ path: path.join(outputDir, filename) });
  frames.push({ filename, duration });
  return filename;
}

async function typeAndCapture(page, selector, text, label) {
  const input = page.locator(selector);
  await input.fill('');
  await input.focus();
  for (const [index, character] of Array.from(text).entries()) {
    await input.pressSequentially(character);
    await capture(page, `typing-${index + 1}`, label, 0.12, 60);
  }
}

async function connect(page, channel, typingLabel) {
  await typeAndCapture(page, '#channel-input', channel, typingLabel);
  await page.locator('#connect-button').click();
  await page.waitForFunction(
    (expected) => document.getElementById('connection-status').textContent === `Subscribed to ${expected}`,
    channel,
    { timeout: 8000 },
  );
  assert.equal(await page.locator('#send-button').isEnabled(), true);
}

async function publish(page, message, subscriberCount, typingLabel) {
  const channel = await page.locator('#channel-input').inputValue();
  const expectedPath = `/channels/${encodeURIComponent(channel)}/messages`;
  await typeAndCapture(page, '#message-input', message, typingLabel);
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === 'POST' && new URL(response.url()).pathname === expectedPath,
    { timeout: 8000 },
  );
  await page.locator('#send-button').click();
  const response = await responsePromise;
  const result = await response.json();
  assert.equal(response.status(), 200);
  assert.deepEqual(result, { channel, subscriber_count: subscriberCount });
  await page.waitForFunction(
    (expected) => document.getElementById('publish-result').textContent === `HTTP 200: ${expected}`,
    JSON.stringify(result),
    { timeout: 8000 },
  );
}

async function verifyMessages(page, expected) {
  await page.waitForFunction(
    (wanted) => {
      const actual = Array.from(document.querySelectorAll('#message-list li'), (item) => item.textContent);
      return actual.length === wanted.length && actual.every((message, index) => message === wanted[index]);
    },
    expected,
    { timeout: 8000 },
  );
  assert.deepEqual(await page.locator('#message-list li').allTextContents(), expected);
}

function buildGif() {
  const list = frames.map(({ filename, duration }) => `file '${filename}'\nduration ${duration}`).join('\n');
  const totalDuration = frames.reduce((total, { duration }) => total + duration, 0);
  fs.writeFileSync(path.join(outputDir, 'frames.txt'), `${list}\nfile '${frames.at(-1).filename}'\n`);
  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'concat', '-safe', '0', '-i', path.join(outputDir, 'frames.txt'),
    '-vf', 'fps=10,scale=960:540:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse=dither=sierra2_4a',
    '-loop', '0', '-t', totalDuration.toFixed(3), path.join(__dirname, 'workflow_full.gif'),
  ], { stdio: 'inherit' });
}

(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  for (const filename of fs.readdirSync(outputDir)) {
    if (/^\d{2,3}-.+\.png$/.test(filename) || filename === 'frames.txt') {
      fs.unlinkSync(path.join(outputDir, filename));
    }
  }

  const browser = await chromium.launch({ headless: false, slowMo: 200 });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
    const openPage = async () => {
      const page = await context.newPage();
      await page.goto('http://127.0.0.1:8000', { waitUntil: 'networkidle' });
      return page;
    };

    // 1. Tab A: one subscriber.
    const pageA = await openPage();
    await connect(pageA, 'notifications', '1/13 TAB A - typing channel: notifications');
    await capture(pageA, 'tab-a-subscribed', '1/13 TAB A - subscribed to notifications; Send enabled');
    await publish(pageA, 'Solo check', 1, '2/13 TAB A - typing message: Solo check');
    await verifyMessages(pageA, ['Solo check']);
    await capture(pageA, 'tab-a-solo-check', '2/13 TAB A - Solo check received once; subscriber_count = 1');

    // 2. Tab B: two-tab fan-out. Tab C must not exist yet.
    const pageB = await openPage();
    await connect(pageB, 'notifications', '3/13 TAB B - typing channel: notifications');
    await capture(pageB, 'tab-b-subscribed', '3/13 TAB B - second notifications subscriber connected');
    await publish(pageA, 'Hello from Redis!', 2, '4/13 TAB A - typing message: Hello from Redis!');
    await verifyMessages(pageA, ['Solo check', 'Hello from Redis!']);
    await verifyMessages(pageB, ['Hello from Redis!']);
    await capture(pageA, 'tab-a-fan-out', '4/13 TAB A - Hello from Redis! received once; subscriber_count = 2');
    await capture(pageB, 'tab-b-fan-out', '5/13 TAB B - Hello from Redis! received exactly once');

    // 3. Tab C: channel isolation, only after the fan-out check.
    const pageC = await openPage();
    await connect(pageC, 'other-channel', '6/13 TAB C - typing channel: other-channel');
    await capture(pageC, 'tab-c-subscribed', '6/13 TAB C - subscribed to other-channel');
    await publish(pageA, 'Channel isolation', 2, '7/13 TAB A - typing message: Channel isolation');
    await verifyMessages(pageA, ['Solo check', 'Hello from Redis!', 'Channel isolation']);
    await verifyMessages(pageB, ['Hello from Redis!', 'Channel isolation']);
    await pageC.waitForTimeout(300);
    await verifyMessages(pageC, []);
    await capture(pageA, 'tab-a-isolation', '7/13 TAB A - Channel isolation received once; subscriber_count = 2');
    await capture(pageB, 'tab-b-isolation', '8/13 TAB B - Channel isolation received exactly once');
    await capture(pageC, 'tab-c-isolation', '9/13 TAB C - no notifications messages received');

    // 4. Disconnect cleanup.
    await pageB.locator('#disconnect-button').click();
    await pageB.waitForFunction(() => document.getElementById('connection-status').textContent === 'Disconnected');
    await capture(pageB, 'tab-b-disconnected', '10/13 TAB B - disconnected; Send disabled');
    await pageA.waitForTimeout(750);
    await publish(pageA, 'After disconnect', 1, '11/13 TAB A - typing message: After disconnect');
    await verifyMessages(pageA, ['Solo check', 'Hello from Redis!', 'Channel isolation', 'After disconnect']);
    await pageB.waitForTimeout(300);
    await verifyMessages(pageB, ['Hello from Redis!', 'Channel isolation']);
    await verifyMessages(pageC, []);
    const finalA = await capture(pageA, 'tab-a-after-disconnect', '11/13 TAB A - After disconnect received once; subscriber_count = 1');
    const finalB = await capture(pageB, 'tab-b-after-disconnect', '12/13 TAB B - no After disconnect message');
    const finalC = await capture(pageC, 'tab-c-after-disconnect', '13/13 TAB C - still no messages');

    for (const [tab, source] of [['A', finalA], ['B', finalB], ['C', finalC]]) {
      fs.copyFileSync(path.join(outputDir, source), path.join(outputDir, `tab${tab}-final.png`));
    }
    buildGif();
    console.log(`PASS: all 4 checks matched; 13 checkpoints and ${frames.length} total captures written to workflow_full.gif.`);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
