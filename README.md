# ⚡ FitCoach AI — Full Stack Setup Guide

## Project Structure
```
fitcoach/
├── backend/           ← Flask API + Web App
│   ├── app.py
│   ├── db.py
│   ├── models.py
│   ├── requirements.txt
│   ├── static/
│   │   ├── style.css
│   │   └── script.js
│   └── templates/
│       └── index.html
│
└── mobile/            ← React Native (Expo)
    ├── App.js
    ├── app.json
    ├── package.json
    └── src/
        ├── screens/
        │   ├── AuthScreen.js
        │   ├── ChatScreen.js
        │   ├── ProgressScreen.js
        │   └── ProfileScreen.js
        ├── services/
        │   └── api.js
        └── theme.js
```

---

## 🖥️ Backend Setup

### 1. Create `.env` file in backend/
```
GROQ_API_KEY=your_groq_api_key_here
JWT_SECRET=any_random_long_string_here
```

### 2. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Run the server
```bash
python app.py
```
Server starts at: `http://localhost:5000`

---

## 📱 Mobile App Setup

### 1. Install Expo CLI
```bash
npm install -g expo-cli
```

### 2. Install dependencies
```bash
cd mobile
npm install
```

### 3. Set your server IP
Edit `src/services/api.js`:
```js
export const BASE_URL = "http://YOUR_LOCAL_IP:5000";
// Example: "http://192.168.1.100:5000"
```
Find your IP with: `ipconfig` (Windows) or `ifconfig` (Mac/Linux)

### 4. Start the app
```bash
npx expo start
```
Scan the QR code with the **Expo Go** app on your phone.

---

## ✨ Features

### Web App
- 🔐 JWT Auth (login / signup)
- 🤖 AI Personal Coach powered by Groq (Llama 3.3 70B)
- 🎤 Voice Input (Web Speech API) + Voice Output (TTS)
- 💪 Full workout flow: start → sets → feedback → log
- ⏱️ Animated rest timer between sets
- 🏋️ Exercise demo cards with muscle group indicators
- 📊 Progress dashboard: weight trend, weekly workouts, heatmap, muscle distribution
- 🏆 Badge system (1, 7, 30, 50, 100 workouts)
- 🎉 Confetti animation on workout completion
- 👤 Profile editor with goal/level/injury tracking

### Mobile App (React Native)
- Everything above, native feel
- Haptic feedback on set completion
- Push-to-speak voice control
- Native charts (react-native-gifted-charts)
- Offline-ready navigation

---

## 🏗️ API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | /api/signup | No | Create account |
| POST | /api/login | No | Get JWT token |
| GET  | /api/me | Yes | Current user info |
| POST | /api/chat | Yes | Send message to coach |
| GET  | /api/progress | Yes | Full analytics data |
| GET  | /api/profile | Yes | Get profile |
| PUT  | /api/profile | Yes | Update profile |
| GET  | /health | No | Server health check |

---

## 💼 Selling to Fitness Chains (Cult, etc.)

The architecture is white-label ready:
1. Change logo/colors in `style.css` (CSS variables in `:root`)
2. Update `GROQ_API_KEY` and trainer prompts per brand
3. Deploy backend to any cloud (Railway, Render, AWS)
4. Publish React Native app under their brand name

**Premium features to pitch:**
- Real-time AI that remembers every workout
- Voice-controlled coaching (hands-free)
- Gender-aware exercise demos
- Streak + badge gamification
- Full analytics dashboard
- Works on web + iOS + Android
