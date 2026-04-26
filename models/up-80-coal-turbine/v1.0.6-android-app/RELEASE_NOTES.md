# v1.0.6 Android Startup Fix

Native Android catalog app source for the UP #80 model kit, rebuilt to avoid startup crashes on phones that dislike newer system-insets APIs.

## Added
- Kept the small `!` update button in the top title row.
- Kept the native update popup with links to the latest GitHub release and the current app release.
- Replaced Android 11+ system-insets calls with legacy immersive flags for broader phone compatibility.
- Standardized spinner layout setup.
- Bottom padding for the app command rows to reduce overlap on gesture and three-button Android navigation.
- Local lightweight preview catalog generated from v1.0.4 STL files.
- Three-shell default preview.
- Full catalog preview.
- GitHub links for each part, each batch, chassis docs, and the full v1.0.4 manufacturing zip.

## Notes
- This is an Android app source release; no full STL files are bundled in the APK assets.
- Printable files for this app revision are in v1.0.4.
- APK building requires Android SDK/Gradle or the included GitHub Actions workflow.
