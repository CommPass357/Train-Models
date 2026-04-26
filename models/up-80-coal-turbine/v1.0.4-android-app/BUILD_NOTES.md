# Build Notes

## Android Studio
1. Open `app-project`.
2. Let Android Studio install missing SDK/build tools if prompted.
3. Build `app`.
4. Install the generated APK on Android.

## Command Line
From `app-project`, run:

```powershell
gradle :app:assembleDebug
```

The app uses plain Java Android APIs and local asset JSON. It has no third-party runtime dependencies.
