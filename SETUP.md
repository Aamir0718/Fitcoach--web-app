# 📱 FitCoach Mobile — Setup Guide (Step by Step)

---

## STEP 1 — Install Node.js
Download from: https://nodejs.org (get the LTS version)
After installing, open terminal and check:
```
node --version
npm --version
```

---

## STEP 2 — Install Expo CLI
```
npm install -g expo-cli eas-cli
```

---

## STEP 3 — Go into the mobile folder
```
cd path/to/fitcoach/mobile
```

---

## STEP 4 — Install all packages
```
npm install
```
Wait for it to finish (takes 2-3 mins first time).

---

## STEP 5 — Set your server IP

Open `src/services/api.js` and change this line:
```js
export const BASE_URL = 'http://192.168.1.100:5000';
```

Replace `192.168.1.100` with YOUR computer's IP address.

**How to find your IP:**
- Windows: Open CMD → type `ipconfig` → look for "IPv4 Address"
- Mac: Open Terminal → type `ifconfig | grep inet`

Make sure your phone and computer are on the SAME WiFi network!

---

## STEP 6 — Start the Expo server
```
npx expo start
```

You'll see a QR code in the terminal.

---

## STEP 7 — Run on your iPhone

### Option A — Expo Go app (easiest)
1. Download **Expo Go** from App Store
2. Open Expo Go → tap **Scan QR Code**
3. Scan the QR code from terminal
4. App opens! ✅

### Option B — Run in browser (no phone needed)
Press `W` in the terminal after running `npx expo start`
Opens in your browser at localhost.

---

## STEP 8 — Make sure your Flask backend is running

In a SEPARATE terminal:
```
cd path/to/fitcoach/backend
python app.py
```

Both backend (port 5000) and Expo must be running at the same time.

---

## ❗ Troubleshooting

**"SDK mismatch" error in Expo Go:**
→ This package uses SDK 52. If your Expo Go shows SDK mismatch,
→ Run: `npx expo start --tunnel`
→ OR update Expo Go from App Store

**"Network request failed":**
→ Check your IP in api.js
→ Make sure backend is running on port 5000
→ Make sure phone + PC are on same WiFi

**"Module not found" errors:**
→ Run `npm install` again
→ Then `npx expo start --clear`

**Charts not showing:**
→ Works after first workout is completed — no data = no charts

---

## 📁 Final Folder Structure

```
mobile/
├── App.js                    ← Main entry, navigation
├── app.json                  ← Expo config
├── babel.config.js           ← Required for reanimated
├── package.json              ← Dependencies
└── src/
    ├── theme.js              ← Colors & radius
    ├── services/
    │   └── api.js            ← API calls (SET YOUR IP HERE)
    └── screens/
        ├── AuthScreen.js     ← Login / Signup
        ├── ChatScreen.js     ← AI Coach chat
        ├── ProgressScreen.js ← Charts & analytics
        └── ProfileScreen.js  ← Edit profile & logout
```
