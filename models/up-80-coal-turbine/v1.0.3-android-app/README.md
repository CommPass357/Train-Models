# UP #80 Android Catalog v1.0.3

This release replaces the web-preview idea with a lean native Android app project.

The app previews lightweight mesh data for the full v1.0.1 kit and opens GitHub links for selected parts, selected batches, the v1.0.1 manufacturing release, and the full v1.0.1 zip.

## Catalog Counts
- Total preview items: 53
- Shells: 3
- Chassis parts: 48
- Details/test items: 2

## App Behavior
- Default view shows the three shell units.
- Full catalog view lays out every preview item.
- Part selector previews one selected item.
- Open part opens the raw GitHub file for that item.
- Open batch opens the GitHub folder for that item's batch.
- Download all opens the v1.0.1 manufacturing zip.

## Build Status
This machine did not have Android SDK/Gradle installed, so no local APK was produced. The repo includes an Android Studio/Gradle project and a GitHub Actions workflow intended to build a debug APK from tag v1.0.3.
