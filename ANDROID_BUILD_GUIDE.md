# SmartWorker — Android APK Build Guide (Cordova)

## How It Works
- Your Flask app runs on Replit's servers (online)
- The Android app wraps it in a native shell via **Apache Cordova**
- **Offline sync**: When there's no internet, data is saved locally on the device. When connection returns, it automatically uploads to the server

---

## What You Need on Your PC
- **Node.js** (v18+) — https://nodejs.org
- **Android Studio** — https://developer.android.com/studio
- **Java JDK 17** — bundled with Android Studio
- **Cordova CLI** — installed in step 4

---

## Step 1: Deploy Your App on Replit

The APK connects to your live server, so deploy first:

1. In Replit, click the **Deploy** button (top right)
2. Follow the prompts — it takes about 2 minutes
3. Copy your public URL: `https://smartworker-yourname.replit.app`

---

## Step 2: Update Your App URL (2 files)

Replace `YOUR_REPLIT_APP_URL` in these two files with your real deployed URL:

**`config.xml`** — find this line:
```xml
<allow-navigation href="https://YOUR_REPLIT_APP_URL.replit.app/*" />
```

**`www/index.html`** — find this line:
```javascript
var APP_URL = 'https://YOUR_REPLIT_APP_URL.replit.app';
```

---

## Step 3: Download Your Project

- In Replit, click the 3-dot menu (⋯) → **Download as ZIP**
- Extract the ZIP on your PC

---

## Step 4: Install Cordova & Set Up Android

Open a terminal in the extracted project folder:

```bash
# Install Cordova globally
npm install -g cordova

# Install project dependencies
npm install

# Add Android platform
cordova platform add android

# Install required plugins
cordova plugin add cordova-plugin-whitelist
cordova plugin add cordova-plugin-network-information
cordova plugin add cordova-plugin-splashscreen
cordova plugin add cordova-plugin-statusbar
cordova plugin add cordova-sqlite-storage
```

---

## Step 5: Build the APK

```bash
# Debug APK (for testing)
cordova build android

# OR Release APK (for distribution)
cordova build android --release
```

Your APK will be at:
```
platforms/android/app/build/outputs/apk/debug/app-debug.apk
```

---

## Step 6: Install on Android Phone

**Option A — USB:**
```bash
cordova run android
```
(Phone must have USB debugging enabled)

**Option B — Manual:**
1. Copy `app-debug.apk` to your phone via USB/email/WhatsApp
2. Open the file on your phone
3. If prompted, allow "Install from unknown sources" in Settings
4. Tap **Install**

---

## Offline Sync — How It Works

Once installed, the app automatically:

| Situation | What happens |
|---|---|
| **Online** | Works normally, data saves to server instantly |
| **Goes offline** | Red banner appears: "You are offline" |
| **Submit form offline** | Data saved on device, yellow toast: "Saved locally" |
| **Back online** | Auto-syncs all pending items, shows count |

Forms that support offline saving:
- Add/Edit Worker
- Mark Attendance
- Any other POST form in the app

---

## Tips
- The APK requires internet to first load — after that, pages are cached
- If you redeploy with a new Replit URL, update `config.xml` and `www/index.html` and rebuild
- For Play Store publishing, use `cordova build android --release` and sign the APK

---

## Troubleshooting

| Error | Fix |
|---|---|
| `ANDROID_HOME not set` | Set Android SDK path in Android Studio → SDK Manager |
| `Gradle build failed` | Run `cordova requirements` to see what's missing |
| `App shows blank screen` | Check the URL in `www/index.html` is correct and deployed |
| `Network error` | Make sure `config.xml` has your real deployed URL in `allow-navigation` |
