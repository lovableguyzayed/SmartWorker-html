# SmartWorker — Android APK Build Guide

## What You Need on Your PC
- **Node.js** (v18+) — https://nodejs.org
- **Android Studio** — https://developer.android.com/studio
- **Java JDK 17** — bundled with Android Studio

---

## Step 1: Deploy Your App on Replit

Before building the APK, your Flask app must be publicly deployed so the APK can connect to it.

1. In Replit, click the **Deploy** button (top right)
2. Follow the prompts to publish
3. Copy your public URL — it will look like: `https://smartworker-yourname.replit.app`

---

## Step 2: Update the App URL

Open `capacitor.config.json` and replace `YOUR_REPLIT_APP_URL` with your real deployed URL:

```json
"server": {
  "url": "https://smartworker-yourname.replit.app"
}
```

Also update `www/index.html` with the same URL.

---

## Step 3: Download Your Project

Download your Replit project as a ZIP file:
- In Replit, click the 3 dots (⋯) menu → **Download as ZIP**
- Extract it on your PC

---

## Step 4: Install Capacitor on Your PC

Open a terminal in the extracted project folder and run:

```bash
npm install
npx cap init
npx cap add android
npx cap sync
```

---

## Step 5: Open in Android Studio

```bash
npx cap open android
```

Android Studio will open. Wait for Gradle to finish syncing (may take a few minutes).

---

## Step 6: Build the APK

In Android Studio:
1. Go to **Build** → **Build Bundle(s) / APK(s)** → **Build APK(s)**
2. Wait for the build to finish
3. Click **Locate** in the popup to find your APK file

The APK will be at:
`android/app/build/outputs/apk/debug/app-debug.apk`

---

## Step 7: Install on Android

Transfer the APK file to your Android phone via USB or email, then:
1. Open the APK file on your phone
2. If prompted, enable **"Install from unknown sources"** in Settings
3. Tap **Install**

SmartWorker will now appear as a native app on your home screen!

---

## Tips
- The APK connects to your Replit server — internet is required to use the app
- If you redeploy with a new URL, you need to rebuild the APK
- For a release APK (not debug), use Build → Generate Signed Bundle/APK in Android Studio
