// Screenshots of batch 1 as built, to set beside the approved mockups.
//
//   node docs/audit/mockups/src/built_batch1.js <app without SMS> <app with SMS_DEV_LOG=1> <its log file>
//
// The second app's log is read for the code, the way a phone reads the SMS.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PLAIN = process.argv[2] || 'http://127.0.0.1:5055';
const OTP = process.argv[3] || 'http://127.0.0.1:5056';
const LOG = process.argv[4];
const OUT = path.join(__dirname, '..');

const lastCode = (mobile) => {
  const lines = fs.readFileSync(LOG, 'utf8').split('\n').filter(l => l.includes('OTP for ' + mobile));
  return lines.length ? lines[lines.length - 1].trim().split(' ').pop() : null;
};

async function phone(browser, opts = {}) {
  const ctx = await browser.newContext({
    viewport: { width: opts.w || 360, height: opts.h || 800 }, deviceScaleFactor: 2,
    isMobile: !opts.tablet, hasTouch: true, serviceWorkers: 'block',
  });
  return ctx.newPage();
}
const big = (p) => p.addStyleTag({ content: 'html{font-size:150% !important}' });
const shot = (p, name, full = true) => p.screenshot({ path: path.join(OUT, name + '.png'), fullPage: full })
  .then(() => console.log('built', name));

(async () => {
  const b = await chromium.launch();

  // Without SMS: what the live site shows today.
  let p = await phone(b);
  await p.goto(PLAIN + '/login', { waitUntil: 'networkidle' });
  await shot(p, 'B1-AUTH_login_built_nosms');
  await p.goto(PLAIN + '/register', { waitUntil: 'networkidle' });
  await shot(p, 'B1-AUTH_register_built_nosms');
  await p.fill('#full_name', 'Ramesh Kumar');
  await p.fill('#mobile', '98765');
  await p.fill('#password', 'short');
  await p.click('#register-btn');
  await p.waitForLoadState('networkidle');
  await p.waitForTimeout(1500);   // let the screen transition finish
  await shot(p, 'B1-AUTH_register_built_error', false);
  await p.goto(PLAIN + '/login', { waitUntil: 'networkidle' });
  await big(p);
  await shot(p, 'B1-AUTH_login_built_nosms_bigfont');
  await p.context().close();

  // With SMS: the approved flow end to end.
  p = await phone(b);
  await p.goto(OTP + '/login', { waitUntil: 'networkidle' });
  await p.fill('#otp-mobile', '+91 98765 43210');
  await shot(p, 'B1-AUTH_login_built');
  await p.click('#otp-send-btn');
  await p.waitForSelector('#otp-code:not([hidden])');
  await p.type('#otp-input', '482');
  await shot(p, 'B1-AUTH_otp_built');
  await p.fill('#otp-input', '');
  await p.type('#otp-input', '000000');
  await p.waitForSelector('#otp-code-msg:not([hidden])');
  await shot(p, 'B1-AUTH_otp_wrong_built');
  await p.fill('#otp-input', '');
  await p.type('#otp-input', lastCode('9876543210'));
  await p.waitForSelector('#otp-details:not([hidden])');
  await p.fill('#d-name', 'Ramesh Kumar');
  await shot(p, 'B1-AUTH_newuser_built');
  await p.click('#otp-details-btn');
  await p.waitForURL(u => !u.pathname.startsWith('/login'));
  await p.waitForTimeout(1500);   // let the screen transition finish
  await shot(p, 'B1-AUTH_after_signup_built', false);
  await p.context().close();

  p = await phone(b);
  await p.goto(OTP + '/login', { waitUntil: 'networkidle' });
  await p.click('[data-show="signin-form"]');
  await shot(p, 'B1-AUTH_password_built');
  await p.context().close();

  // Hindi, large text, tablet.
  p = await phone(b);
  await p.goto(OTP + '/login', { waitUntil: 'networkidle' });
  await p.click('.sw-lang button[lang="hi"]');
  await p.waitForLoadState('networkidle');
  await p.fill('#otp-mobile', '9876543210');
  await shot(p, 'B1-AUTH_login_built_hindi');
  await p.context().close();

  p = await phone(b);
  await p.goto(OTP + '/login', { waitUntil: 'networkidle' });
  await big(p);
  await p.fill('#otp-mobile', '9876543210');
  await shot(p, 'B1-AUTH_login_built_bigfont');
  await p.context().close();

  p = await phone(b, { w: 768, h: 1024, tablet: true });
  await p.goto(OTP + '/login', { waitUntil: 'networkidle' });
  await p.fill('#otp-mobile', '9876543210');
  await shot(p, 'B1-AUTH_login_built_tablet', false);
  await p.context().close();

  await b.close();
})();
