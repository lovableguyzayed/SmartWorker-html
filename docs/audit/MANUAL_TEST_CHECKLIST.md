# Manual test checklist

These need a real phone, a real SIM or a real store. None of them can be
done in the cloud machine the audit ran on. Tick each one off as you go.

**How to get the newest test APK:** GitHub → Actions → *Build Android APK*
→ the latest run on this branch → *Artifacts* → `SmartWorker-debug-apk`
(sign in to GitHub, unzip, install). Builds from `main` also appear at
the usual one-tap link: `…/releases/latest/download/SmartWorker.apk`.

## 1. The Android app (most important, new in this round)

Install the API 36 build over the old app (keep your data), then:

- [ ] **Save PDF works.** Payroll → a worker → Payslip → *Save PDF*. A PDF
      viewer should open with the payslip. *(NAT-01: before this round it
      most likely did nothing.)*
- [ ] **Excel works.** Payroll → *Download Excel*. The file opens.
- [ ] **ID card PDF/PNG works.** Worker → ID card → Download → PDF.
- [ ] **Back button.** Open a dialog (e.g. Attendance → tap a worker's
      adjust). Press Back: the dialog closes, the screen stays. On the Home
      tab, press Back once: "Press back again to exit". Press again: closes.
- [ ] **Back gesture** (swipe from the screen edge, Android 13+): same as above.
- [ ] **Camera is asked only when scanning.** Fresh install → open the app:
      no camera prompt. Tap *Scan QR* → the prompt appears then. Deny it once,
      then try again: the scanner should say the camera is blocked, not
      show a black box.
- [ ] **No notification prompt** at any point.
- [ ] **Status bar** is navy with white icons; nothing is hidden under it or
      under the gesture bar / 3-button bar at the bottom.
- [ ] **Old saved files** (exports saved before this update) are still in
      the phone's Files app.

## 2. Sign in and sign up

Today (no SMS provider connected):
- [ ] Sign in with username + password, and with **mobile number + password**
      (try typing `+91 98765 43210`, `098765 43210` and `9876543210`).
- [ ] Create account with name + mobile + password only (no email).
- [ ] Wrong password 8 times → the 9th try says to wait 15 minutes.
- [ ] Sign out from Profile, then press Back: you must not see the dashboard.

After an SMS provider is connected (decision D1):
- [ ] OTP arrives on **Jio, Airtel, Vi and BSNL** numbers, and on SIM 2 of a
      dual-SIM phone.
- [ ] The phone offers the code above the keyboard (one tap fills it).
- [ ] Wrong code says how many tries are left; 5 wrong → wait.
- [ ] Leave the app to read the SMS, come back: the code screen is still there.
- [ ] Same with *Developer options → Don't keep activities* turned on (a
      low-RAM phone killing the app while you read the SMS).
- [ ] A new number goes to "Welcome! One last step"; an existing one signs
      straight in.

## 3. Phones and settings

Test on at least: one budget Android (2–3 GB RAM, Android 10–11), one
mid-range Android (Android 14+), one 7–10" tablet if you have one.

- [ ] **Largest font + largest display size** (Settings → Display). Sign in,
      Attendance, Worker profile, Payroll, Payslip. Note any screen that
      scrolls sideways or cuts text. *(Known: batch 2 fixes Attendance and
      the bottom tabs once approved.)*
- [ ] **Xiaomi / Redmi with dark mode on** (MIUI/HyperOS): the app must stay
      light and readable.
- [ ] **Slow network:** Developer options or a weak signal. Mark attendance,
      open payroll. Nothing should spin forever; offline marks should sync
      when the signal returns.
- [ ] **Airplane mode** mid-action: a clear message, no lost input.
- [ ] **Tablet / unfolded foldable, landscape:** Android 16 ignores the
      portrait lock on large screens. Check nothing is stretched or cut.
- [ ] **16 KB page size:** run once on an Android 15+ emulator image with
      16 KB pages (Android Studio → Device Manager). The app has no native
      libraries of its own, so this should pass.
- [ ] **First open after a quiet hour** (Render free plan wakes up): time it.
      If it is over ~10 s, see decision D7.

## 4. Printing and sharing

- [ ] Print a payslip and an ID card on a real printer (A4).
- [ ] Scan the printed ID card's QR with the app's scanner (English and Hindi cards).
- [ ] Share a payslip PDF to WhatsApp (after NAT-01 is confirmed).

---

# Before a Play Store release

| | Item | Status |
|---|---|---|
| ☑ | Target API 36 (required since 31 Aug 2026) | Done on this branch; build passes |
| ☐ | **Release signing key** — make one, keep it safe forever (losing it = never updating the app again). Prefer Play App Signing. | Owner (D8) |
| ☐ | Build a signed **AAB** (not a debug APK) in CI, with the key as a GitHub secret | To do after D8 |
| ☐ | `android-versionCode` set in config.xml and raised on every release | To do with release build |
| ☐ | 16 KB page-size check (section 3) | Manual |
| ☐ | **Privacy Policy** page, reachable from the sign-in screen and Settings, and its URL in Play Console | Owner (D3) |
| ☐ | **Delete account** in the app **and** a web page that works without the app | To do after D3 |
| ☐ | **Data Safety form**: name, phone, email (optional), photos, financial info (wages, UPI/bank), camera (QR scanning). No location. Data is encrypted in transit (HTTPS). | Owner, in Play Console |
| ☐ | Billing policy: nothing is sold in the app, so Play Billing does **not** apply. Re-check if subscriptions are ever added. | No action today |
| ☐ | New personal developer account: **closed test with at least 12 testers for 14 days** before production | Owner |
| ☐ | Store listing: screenshots (phone + 7"/10" tablet), short and full description in English and Hindi, app icon 512×512 | Owner |
| ☐ | Make the GitHub repository **private** and change any password that was ever in it (D2) | Owner — do first |
