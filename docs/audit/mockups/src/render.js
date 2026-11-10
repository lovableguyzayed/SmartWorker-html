// Renders the mockups to PNG and screenshots the matching screens of the
// running app, so every "after" sits next to a real "before".
//
//   node docs/audit/mockups/src/render.js [app-url]
//
// app-url defaults to http://127.0.0.1:5055 (a copy running on the test
// fixture, see tools/make_test_fixture.py).
const { chromium } = require('playwright');
const path = require('path');

const APP = process.argv[2] || 'http://127.0.0.1:5055';
const HERE = __dirname;
const OUT = path.join(HERE, '..');

// mockup file -> [element id, output name, large font?]
const MOCKS = {
  'batch1_signin.html': [
    ['login_after', 'B1-AUTH_login_after'],
    ['login_after_hi', 'B1-AUTH_login_after_hindi'],
    ['otp_after', 'B1-AUTH_otp_after'],
    ['otp_wrong_after', 'B1-AUTH_otp_wrong_after'],
    ['newuser_after', 'B1-AUTH_newuser_after'],
    ['password_after', 'B1-AUTH_password_after'],
    ['login_after_tablet', 'B1-AUTH_login_after_tablet'],
    ['login_after', 'B1-AUTH_login_after_bigfont', true],
    ['otp_after', 'B1-AUTH_otp_after_bigfont', true],
  ],
};

// before shots: [path, output name, full page?, large font?]
const BEFORE = {
  public: [
    ['/login', 'B1-AUTH_login_before', true],
    ['/register', 'B1-AUTH_register_before', true],
    ['/forgot-password', 'B1-AUTH_forgot_before', false],
    ['/login', 'B1-AUTH_login_before_bigfont', true, true],
  ],
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 2 });
  for (const [file, shots] of Object.entries(MOCKS)) {
    await page.goto('file://' + path.join(HERE, file));
    await page.evaluate(() => document.fonts.ready);
    for (const [id, name, big] of shots) {
      await page.evaluate(b => { document.documentElement.style.fontSize = b ? '150%' : ''; }, !!big);
      await page.waitForTimeout(100);
      await page.locator('#' + id).screenshot({ path: path.join(OUT, name + '.png') });
      console.log('after ', name);
    }
  }
  const phone = await browser.newPage({ viewport: { width: 360, height: 800 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  for (const [p, name, full, big] of BEFORE.public) {
    await phone.goto(APP + p, { waitUntil: 'networkidle' });
    if (big) await phone.addStyleTag({ content: 'html{font-size:150% !important}' });
    await phone.waitForTimeout(300);
    await phone.screenshot({ path: path.join(OUT, name + '.png'), fullPage: !!full });
    console.log('before', name);
  }
  await browser.close();
})();
