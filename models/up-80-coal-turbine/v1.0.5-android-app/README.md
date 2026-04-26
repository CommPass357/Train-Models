# UP #80 Android Catalog v1.0.5

This release adds a tiny in-app GitHub update button and keeps the catalog pointed at the v1.0.4 manufacturing package.

The app previews lightweight mesh data for the full v1.0.4 kit and opens GitHub links for selected parts, selected batches, the v1.0.4 manufacturing release, and the full v1.0.4 zip.

## Catalog Counts
- Total preview items: 53
- Shells: 3
- Chassis parts: 48
- Details/test items: 2

## App Behavior
- Small `!` button opens a native update popup with GitHub release links.
- Default view shows the three shell units.
- Full catalog view lays out every preview item.
- Part selector previews one selected item.
- Open part opens the raw GitHub file for that item.
- Open batch opens the GitHub folder for that item's batch.
- Download all opens the v1.0.4 manufacturing zip.
- Android system navigation uses immersive mode; swipe from the edge to temporarily reveal phone Back/Home/Recents.

## Build Status
This machine did not have Android SDK/Gradle installed, so no local APK was produced. The repo includes an Android Studio/Gradle project and a GitHub Actions workflow intended to build a debug APK from tag v1.0.5.
