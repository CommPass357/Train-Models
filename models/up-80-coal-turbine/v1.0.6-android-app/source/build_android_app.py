from __future__ import annotations

import json
import math
import re
import shutil
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT.parent
REPO_ROOT = ROOT.parents[2]
SOURCE_VERSION = "v1.0.4"
APP_VERSION = "v1.0.6"
SOURCE_ROOT = MODEL_ROOT / SOURCE_VERSION
PACKAGE = "com.commpass.trainmodels.up80"
BASE_GITHUB = "https://github.com/CommPass357/Train-Models"
RAW_BASE = "https://raw.githubusercontent.com/CommPass357/Train-Models/main/models/up-80-coal-turbine"
FULL_ZIP = f"{BASE_GITHUB}/releases/download/{SOURCE_VERSION}/up-80-coal-turbine-ho-{SOURCE_VERSION}.zip"


def ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def clean() -> None:
    ensure(ROOT / "app-project")
    ensure(ROOT / "release")


def parse_ascii_stl(path: Path) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    triangles = []
    current = []
    vertex_re = re.compile(r"^\s*vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)")
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            match = vertex_re.match(line)
            if not match:
                continue
            current.append(tuple(float(match.group(i)) for i in range(1, 4)))
            if len(current) == 3:
                triangles.append((current[0], current[1], current[2]))
                current = []
    return triangles


def bounds_for_positions(positions: list[float]) -> dict:
    xs = positions[0::3]
    ys = positions[1::3]
    zs = positions[2::3]
    mn = [min(xs), min(ys), min(zs)]
    mx = [max(xs), max(ys), max(zs)]
    return {
        "min": mn,
        "max": mx,
        "size": [mx[i] - mn[i] for i in range(3)],
        "center": [(mn[i] + mx[i]) / 2 for i in range(3)],
    }


def simplified_mesh(path: Path, max_triangles: int) -> dict:
    triangles = parse_ascii_stl(path)
    if not triangles:
        raise ValueError(f"No triangles found in {path}")
    step = max(1, math.ceil(len(triangles) / max_triangles))
    sampled = triangles[::step][:max_triangles]
    positions: list[float] = []
    for tri in sampled:
        for vertex in tri:
            positions.extend(round(coord, 3) for coord in vertex)
    return {
        "positions": positions,
        "sourceTriangles": len(triangles),
        "previewTriangles": len(sampled),
        "bounds": bounds_for_positions(positions),
    }


def title_case(stem: str) -> str:
    words = stem.replace("up80_", "").replace("_", " ").split()
    return " ".join(w.upper() if w in {"a"} else w.capitalize() for w in words)


def batch_url_for(group: str, unit: str) -> str:
    if group == "Shells":
        return f"{BASE_GITHUB}/tree/main/models/up-80-coal-turbine/{SOURCE_VERSION}/exports/stl/shells"
    if group == "Details":
        return f"{BASE_GITHUB}/tree/main/models/up-80-coal-turbine/{SOURCE_VERSION}/exports/stl/details"
    return f"{BASE_GITHUB}/tree/main/models/up-80-coal-turbine/{SOURCE_VERSION}/exports/stl/chassis_parts/{unit}"


def gather_parts() -> list[dict]:
    validation = json.loads((SOURCE_ROOT / "validation_report.json").read_text(encoding="utf-8"))
    parts: list[dict] = []
    order = 0
    for rel in validation["shell_stl_files"]:
        path = SOURCE_ROOT / rel
        unit = path.stem.replace("_shell", "")
        parts.append({
            "id": path.stem,
            "label": title_case(path.stem),
            "group": "Shells",
            "unit": unit,
            "sourcePath": rel,
            "partUrl": f"{RAW_BASE}/{SOURCE_VERSION}/{rel}",
            "batchUrl": batch_url_for("Shells", unit),
            "path": path,
            "order": order,
            "maxTriangles": 1200,
            "color": {"a_control": "#F2C94C", "center_turbine": "#BFC5C3", "coal_tender": "#303338"}.get(unit, "#D8D8D8"),
        })
        order += 1
    for unit, rels in validation["chassis_part_index"].items():
        group = f"Chassis - {title_case(unit)}"
        for rel in rels:
            path = SOURCE_ROOT / rel
            parts.append({
                "id": path.stem,
                "label": title_case(path.stem),
                "group": group,
                "unit": unit,
                "sourcePath": rel,
                "partUrl": f"{RAW_BASE}/{SOURCE_VERSION}/{rel}",
                "batchUrl": batch_url_for(group, unit),
                "path": path,
                "order": order,
                "maxTriangles": 420 if "base_plate" not in path.stem and "sideframes" not in path.stem else 760,
                "color": {"a_control": "#51708C", "center_turbine": "#69747D", "coal_tender": "#5F5142"}.get(unit, "#686868"),
            })
            order += 1
    for rel in ["exports/stl/details/up80_detail_sprue.stl", "exports/stl/details/up80_test_coupons.stl"]:
        path = SOURCE_ROOT / rel
        parts.append({
            "id": path.stem,
            "label": title_case(path.stem),
            "group": "Details",
            "unit": "details",
            "sourcePath": rel,
            "partUrl": f"{RAW_BASE}/{SOURCE_VERSION}/{rel}",
            "batchUrl": batch_url_for("Details", "details"),
            "path": path,
            "order": order,
            "maxTriangles": 900,
            "color": "#B08C5A",
        })
        order += 1
    return parts


def shell_offsets(meshes: dict[str, dict]) -> dict[str, list[float]]:
    ids = ["a_control_shell", "center_turbine_shell", "coal_tender_shell"]
    gap = 8.0
    lengths = [meshes[i]["bounds"]["size"][0] for i in ids]
    a_x = -lengths[1] / 2 - gap - lengths[0] / 2
    tender_x = lengths[1] / 2 + gap + lengths[2] / 2
    return {
        "a_control_shell": [round(a_x, 3), 0.0, 0.0],
        "center_turbine_shell": [0.0, 0.0, 0.0],
        "coal_tender_shell": [round(tender_x, 3), 0.0, 0.0],
    }


def build_catalog(parts: list[dict]) -> dict:
    meshes: dict[str, dict] = {}
    catalog_parts = []
    for part in parts:
        mesh = simplified_mesh(part["path"], part["maxTriangles"])
        mesh["color"] = part["color"]
        meshes[part["id"]] = mesh
        catalog_parts.append({
            "id": part["id"],
            "label": part["label"],
            "group": part["group"],
            "unit": part["unit"],
            "sourcePath": part["sourcePath"],
            "partUrl": part["partUrl"],
            "batchUrl": part["batchUrl"],
            "sourceTriangles": mesh["sourceTriangles"],
            "previewTriangles": mesh["previewTriangles"],
            "bounds": mesh["bounds"],
            "color": part["color"],
            "order": part["order"],
        })
    return {
        "project": "UP #80 Coal Turbine Android Catalog",
        "version": APP_VERSION,
        "sourceVersion": SOURCE_VERSION,
        "generatedUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "defaultView": ["a_control_shell", "center_turbine_shell", "coal_tender_shell"],
        "shellOffsets": shell_offsets(meshes),
        "links": {
            "manufacturingRelease": f"{BASE_GITHUB}/releases/tag/{SOURCE_VERSION}",
            "manufacturingZip": FULL_ZIP,
            "repoFolder": f"{BASE_GITHUB}/tree/main/models/up-80-coal-turbine/{SOURCE_VERSION}",
            "chassisPartsDoc": f"{BASE_GITHUB}/blob/main/models/up-80-coal-turbine/{SOURCE_VERSION}/docs/CHASSIS_PARTS.md",
        },
        "parts": catalog_parts,
        "meshes": meshes,
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8", newline="\n")


def write_project(catalog: dict) -> None:
    project = ROOT / "app-project"
    app = project / "app"
    package_dir = app / "src" / "main" / "java" / Path(PACKAGE.replace(".", "/"))
    ensure(package_dir)
    ensure(app / "src" / "main" / "assets")
    write_text(project / "settings.gradle", """
        pluginManagement {
            repositories {
                google()
                mavenCentral()
                gradlePluginPortal()
            }
        }
        dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }
        rootProject.name = 'UP80AndroidCatalog'
        include ':app'
    """)
    write_text(project / "build.gradle", """
        plugins {
            id 'com.android.application' version '8.7.3' apply false
        }
    """)
    write_text(app / "build.gradle", """
        plugins { id 'com.android.application' }

        android {
            namespace 'com.commpass.trainmodels.up80'
            compileSdk 35

            defaultConfig {
                applicationId 'com.commpass.trainmodels.up80'
                minSdk 23
                targetSdk 35
                versionCode 6
                versionName '1.0.6'
            }
        }
    """)
    write_text(app / "src" / "main" / "AndroidManifest.xml", f"""
        <manifest xmlns:android="http://schemas.android.com/apk/res/android">
            <application
                android:allowBackup="true"
                android:label="UP80 Catalog"
                android:theme="@style/AppTheme"
                android:resizeableActivity="true">
                <activity
                    android:name=".{PACKAGE.split('.')[-1]}.MainActivity"
                    android:exported="true"
                    android:screenOrientation="unspecified">
                    <intent-filter>
                        <action android:name="android.intent.action.MAIN" />
                        <category android:name="android.intent.category.LAUNCHER" />
                    </intent-filter>
                </activity>
            </application>
        </manifest>
    """.replace(f".{PACKAGE.split('.')[-1]}.MainActivity", ".MainActivity"))
    write_text(app / "src" / "main" / "res" / "values" / "styles.xml", """
        <resources>
            <style name="AppTheme" parent="android:style/Theme.Material.Light.NoActionBar">
                <item name="android:fontFamily">sans</item>
                <item name="android:windowActionModeOverlay">true</item>
                <item name="android:colorAccent">#4f6f8f</item>
            </style>
        </resources>
    """)
    (app / "src" / "main" / "assets" / "catalog.json").write_text(json.dumps(catalog, separators=(",", ":")), encoding="utf-8")
    write_java(package_dir)


def write_java(package_dir: Path) -> None:
    write_text(package_dir / "CatalogItem.java", """
        package com.commpass.trainmodels.up80;

        final class CatalogItem {
            final String id;
            final String label;
            final String group;
            final String unit;
            final String partUrl;
            final String batchUrl;
            final int sourceTriangles;
            final int previewTriangles;
            final MeshData mesh;

            CatalogItem(String id, String label, String group, String unit, String partUrl, String batchUrl,
                        int sourceTriangles, int previewTriangles, MeshData mesh) {
                this.id = id;
                this.label = label;
                this.group = group;
                this.unit = unit;
                this.partUrl = partUrl;
                this.batchUrl = batchUrl;
                this.sourceTriangles = sourceTriangles;
                this.previewTriangles = previewTriangles;
                this.mesh = mesh;
            }

            @Override public String toString() {
                return group + " / " + label;
            }
        }
    """)
    write_text(package_dir / "MeshData.java", """
        package com.commpass.trainmodels.up80;

        final class MeshData {
            final float[] positions;
            final float[] boundsMin;
            final float[] boundsMax;
            final int color;

            MeshData(float[] positions, float[] boundsMin, float[] boundsMax, int color) {
                this.positions = positions;
                this.boundsMin = boundsMin;
                this.boundsMax = boundsMax;
                this.color = color;
            }
        }
    """)
    write_text(package_dir / "PreviewItem.java", """
        package com.commpass.trainmodels.up80;

        final class PreviewItem {
            final CatalogItem item;
            final float[] offset;

            PreviewItem(CatalogItem item, float[] offset) {
                this.item = item;
                this.offset = offset;
            }
        }
    """)
    write_text(package_dir / "CatalogData.java", """
        package com.commpass.trainmodels.up80;

        import java.util.ArrayList;
        import java.util.HashMap;
        import java.util.List;
        import java.util.Map;

        final class CatalogData {
            String version;
            String sourceVersion;
            String manufacturingReleaseUrl;
            String manufacturingZipUrl;
            String repoFolderUrl;
            String chassisPartsDocUrl;
            final List<CatalogItem> parts = new ArrayList<>();
            final Map<String, CatalogItem> byId = new HashMap<>();
            final Map<String, float[]> shellOffsets = new HashMap<>();
        }
    """)
    write_text(package_dir / "CatalogLoader.java", r"""
        package com.commpass.trainmodels.up80;

        import android.content.Context;
        import android.graphics.Color;
        import org.json.JSONArray;
        import org.json.JSONObject;
        import java.io.ByteArrayOutputStream;
        import java.io.InputStream;

        final class CatalogLoader {
            static CatalogData load(Context context) throws Exception {
                String json = readAsset(context, "catalog.json");
                JSONObject root = new JSONObject(json);
                CatalogData data = new CatalogData();
                data.version = root.getString("version");
                data.sourceVersion = root.getString("sourceVersion");
                JSONObject links = root.getJSONObject("links");
                data.manufacturingReleaseUrl = links.getString("manufacturingRelease");
                data.manufacturingZipUrl = links.getString("manufacturingZip");
                data.repoFolderUrl = links.getString("repoFolder");
                data.chassisPartsDocUrl = links.getString("chassisPartsDoc");

                JSONObject offsets = root.getJSONObject("shellOffsets");
                JSONArray names = offsets.names();
                if (names != null) {
                    for (int i = 0; i < names.length(); i++) {
                        String id = names.getString(i);
                        data.shellOffsets.put(id, floats(offsets.getJSONArray(id)));
                    }
                }

                JSONObject meshes = root.getJSONObject("meshes");
                JSONArray parts = root.getJSONArray("parts");
                for (int i = 0; i < parts.length(); i++) {
                    JSONObject part = parts.getJSONObject(i);
                    String id = part.getString("id");
                    JSONObject meshObject = meshes.getJSONObject(id);
                    JSONObject bounds = meshObject.getJSONObject("bounds");
                    MeshData mesh = new MeshData(
                        floats(meshObject.getJSONArray("positions")),
                        floats(bounds.getJSONArray("min")),
                        floats(bounds.getJSONArray("max")),
                        Color.parseColor(part.getString("color"))
                    );
                    CatalogItem item = new CatalogItem(
                        id,
                        part.getString("label"),
                        part.getString("group"),
                        part.getString("unit"),
                        part.getString("partUrl"),
                        part.getString("batchUrl"),
                        part.getInt("sourceTriangles"),
                        part.getInt("previewTriangles"),
                        mesh
                    );
                    data.parts.add(item);
                    data.byId.put(id, item);
                }
                return data;
            }

            private static String readAsset(Context context, String name) throws Exception {
                InputStream input = context.getAssets().open(name);
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
                input.close();
                return output.toString("UTF-8");
            }

            private static float[] floats(JSONArray array) throws Exception {
                float[] out = new float[array.length()];
                for (int i = 0; i < array.length(); i++) out[i] = (float) array.getDouble(i);
                return out;
            }
        }
    """)
    write_text(package_dir / "MeshPreviewView.java", r"""
        package com.commpass.trainmodels.up80;

        import android.content.Context;
        import android.graphics.Canvas;
        import android.graphics.Color;
        import android.graphics.Paint;
        import android.graphics.Path;
        import android.view.MotionEvent;
        import android.view.View;
        import java.util.ArrayList;
        import java.util.List;

        public final class MeshPreviewView extends View {
            private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
            private final Paint edge = new Paint(Paint.ANTI_ALIAS_FLAG);
            private final List<PreviewItem> items = new ArrayList<>();
            private float rotX = -0.55f;
            private float rotY = 0.72f;
            private float zoom = 1.0f;
            private float centerX;
            private float centerY;
            private float centerZ;
            private float modelSize = 1.0f;
            private float lastX;
            private float lastY;
            private float lastDistance;

            public MeshPreviewView(Context context) {
                super(context);
                setBackgroundColor(Color.rgb(18, 20, 22));
                fill.setStyle(Paint.Style.FILL);
                fill.setAlpha(130);
                edge.setStyle(Paint.Style.STROKE);
                edge.setStrokeWidth(1.0f);
                edge.setColor(Color.argb(170, 20, 20, 20));
            }

            public void setPreviewItems(List<PreviewItem> next) {
                items.clear();
                items.addAll(next);
                fitToItems();
                invalidate();
            }

            public void resetCamera() {
                rotX = -0.55f;
                rotY = 0.72f;
                zoom = 1.0f;
                invalidate();
            }

            private void fitToItems() {
                if (items.isEmpty()) return;
                float minX = Float.MAX_VALUE, minY = Float.MAX_VALUE, minZ = Float.MAX_VALUE;
                float maxX = -Float.MAX_VALUE, maxY = -Float.MAX_VALUE, maxZ = -Float.MAX_VALUE;
                for (PreviewItem preview : items) {
                    MeshData mesh = preview.item.mesh;
                    float ox = preview.offset[0], oy = preview.offset[1], oz = preview.offset[2];
                    minX = Math.min(minX, mesh.boundsMin[0] + ox);
                    minY = Math.min(minY, mesh.boundsMin[1] + oy);
                    minZ = Math.min(minZ, mesh.boundsMin[2] + oz);
                    maxX = Math.max(maxX, mesh.boundsMax[0] + ox);
                    maxY = Math.max(maxY, mesh.boundsMax[1] + oy);
                    maxZ = Math.max(maxZ, mesh.boundsMax[2] + oz);
                }
                centerX = (minX + maxX) * 0.5f;
                centerY = (minY + maxY) * 0.5f;
                centerZ = (minZ + maxZ) * 0.5f;
                modelSize = Math.max(1.0f, Math.max(maxX - minX, Math.max(maxY - minY, maxZ - minZ)));
            }

            @Override protected void onDraw(Canvas canvas) {
                super.onDraw(canvas);
                if (items.isEmpty()) return;
                float baseScale = Math.min(getWidth(), getHeight()) * 0.72f / modelSize * zoom;
                float sx = getWidth() * 0.5f;
                float sy = getHeight() * 0.55f;
                float cx = (float) Math.cos(rotX), sxr = (float) Math.sin(rotX);
                float cy = (float) Math.cos(rotY), syr = (float) Math.sin(rotY);
                Path path = new Path();
                for (PreviewItem preview : items) {
                    MeshData mesh = preview.item.mesh;
                    fill.setColor(mesh.color);
                    fill.setAlpha(128);
                    float[] p = mesh.positions;
                    for (int i = 0; i < p.length; i += 9) {
                        float[] a = project(p[i], p[i + 1], p[i + 2], preview.offset, cx, sxr, cy, syr, baseScale, sx, sy);
                        float[] b = project(p[i + 3], p[i + 4], p[i + 5], preview.offset, cx, sxr, cy, syr, baseScale, sx, sy);
                        float[] c = project(p[i + 6], p[i + 7], p[i + 8], preview.offset, cx, sxr, cy, syr, baseScale, sx, sy);
                        path.reset();
                        path.moveTo(a[0], a[1]);
                        path.lineTo(b[0], b[1]);
                        path.lineTo(c[0], c[1]);
                        path.close();
                        canvas.drawPath(path, fill);
                        canvas.drawPath(path, edge);
                    }
                }
            }

            private float[] project(float x, float y, float z, float[] offset, float cx, float sxr, float cy, float syr,
                                    float scale, float screenX, float screenY) {
                x = x + offset[0] - centerX;
                y = y + offset[1] - centerY;
                z = z + offset[2] - centerZ;
                float x1 = x * cy + z * syr;
                float z1 = -x * syr + z * cy;
                float y1 = y * cx - z1 * sxr;
                return new float[] { screenX + x1 * scale, screenY - y1 * scale };
            }

            @Override public boolean onTouchEvent(MotionEvent event) {
                if (event.getPointerCount() == 1) {
                    if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
                        lastX = event.getX();
                        lastY = event.getY();
                    } else if (event.getActionMasked() == MotionEvent.ACTION_MOVE) {
                        float x = event.getX();
                        float y = event.getY();
                        rotY += (x - lastX) * 0.008f;
                        rotX += (y - lastY) * 0.008f;
                        lastX = x;
                        lastY = y;
                        invalidate();
                    }
                    lastDistance = 0f;
                    return true;
                }
                if (event.getPointerCount() >= 2) {
                    float dx = event.getX(0) - event.getX(1);
                    float dy = event.getY(0) - event.getY(1);
                    float distance = (float) Math.sqrt(dx * dx + dy * dy);
                    if (lastDistance > 0f) zoom *= Math.max(0.75f, Math.min(1.25f, distance / lastDistance));
                    lastDistance = distance;
                    invalidate();
                    return true;
                }
                return true;
            }
        }
    """)
    write_text(package_dir / "MainActivity.java", r"""
        package com.commpass.trainmodels.up80;

        import android.app.Activity;
        import android.app.AlertDialog;
        import android.content.Intent;
        import android.graphics.Color;
        import android.net.Uri;
        import android.os.Bundle;
        import android.view.View;
        import android.view.Window;
        import android.widget.AdapterView;
        import android.widget.ArrayAdapter;
        import android.widget.Button;
        import android.widget.LinearLayout;
        import android.widget.Spinner;
        import android.widget.TextView;
        import android.widget.Toast;
        import java.util.ArrayList;
        import java.util.List;

        public final class MainActivity extends Activity {
            private static final String APP_RELEASE_URL = "https://github.com/CommPass357/Train-Models/releases/tag/v1.0.6";
            private static final String LATEST_RELEASE_URL = "https://github.com/CommPass357/Train-Models/releases/latest";
            private CatalogData catalog;
            private MeshPreviewView preview;
            private Spinner spinner;
            private TextView title;
            private TextView info;
            private CatalogItem selected;

            @Override protected void onCreate(Bundle state) {
                super.onCreate(state);
                enableImmersiveMode();
                try {
                    catalog = CatalogLoader.load(this);
                } catch (Exception e) {
                    TextView error = new TextView(this);
                    error.setText("Could not load catalog: " + e.getMessage());
                    setContentView(error);
                    return;
                }

                LinearLayout root = new LinearLayout(this);
                root.setOrientation(LinearLayout.VERTICAL);
                root.setPadding(dp(12), dp(12), dp(12), dp(34));

                LinearLayout titleRow = new LinearLayout(this);
                titleRow.setOrientation(LinearLayout.HORIZONTAL);
                titleRow.setPadding(0, 0, 0, dp(8));

                title = new TextView(this);
                title.setText("UP #80 Catalog v1.0.6");
                title.setTextSize(20);
                title.setPadding(0, 0, dp(8), 0);
                title.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
                titleRow.addView(title);

                Button update = iconButton("!", v -> showUpdateDialog());
                titleRow.addView(update);
                root.addView(titleRow);

                preview = new MeshPreviewView(this);
                root.addView(preview, new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));

                spinner = new Spinner(this);
                ArrayAdapter<CatalogItem> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, catalog.parts);
                adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
                spinner.setAdapter(adapter);
                root.addView(spinner);

                info = new TextView(this);
                info.setPadding(0, 8, 0, 8);
                root.addView(info);

                LinearLayout row1 = row();
                row1.addView(button("3 shells", v -> showShells()));
                row1.addView(button("Full catalog", v -> showFullCatalog()));
                row1.addView(button("Reset", v -> preview.resetCamera()));
                root.addView(row1);

                LinearLayout row2 = row();
                row2.addView(button("Preview part", v -> showSelected()));
                row2.addView(button("Open part", v -> open(selected.partUrl)));
                row2.addView(button("Open batch", v -> open(selected.batchUrl)));
                root.addView(row2);

                LinearLayout row3 = row();
                row3.addView(button("Download all", v -> open(catalog.manufacturingZipUrl)));
                row3.addView(button("v1.0.4 files", v -> open(catalog.manufacturingReleaseUrl)));
                row3.addView(button("Chassis docs", v -> open(catalog.chassisPartsDocUrl)));
                root.addView(row3);

                setContentView(root);
                root.post(this::enableImmersiveMode);
                selected = catalog.parts.get(0);
                spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
                    @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                        selected = catalog.parts.get(position);
                        updateInfo(selected);
                    }
                    @Override public void onNothingSelected(AdapterView<?> parent) {}
                });
                showShells();
            }

            @Override public void onWindowFocusChanged(boolean hasFocus) {
                super.onWindowFocusChanged(hasFocus);
                if (hasFocus) enableImmersiveMode();
            }

            private void enableImmersiveMode() {
                Window window = getWindow();
                window.setStatusBarColor(Color.TRANSPARENT);
                window.setNavigationBarColor(Color.TRANSPARENT);
                window.getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                );
            }

            private int dp(int value) {
                return Math.round(value * getResources().getDisplayMetrics().density);
            }

            private LinearLayout row() {
                LinearLayout row = new LinearLayout(this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                return row;
            }

            private Button button(String text, View.OnClickListener listener) {
                Button button = new Button(this);
                button.setText(text);
                button.setAllCaps(false);
                button.setOnClickListener(listener);
                button.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
                return button;
            }

            private Button iconButton(String text, View.OnClickListener listener) {
                Button button = new Button(this);
                button.setText(text);
                button.setTextSize(14);
                button.setAllCaps(false);
                button.setMinWidth(0);
                button.setMinimumWidth(0);
                button.setPadding(0, 0, 0, 0);
                button.setOnClickListener(listener);
                button.setLayoutParams(new LinearLayout.LayoutParams(dp(34), dp(34)));
                return button;
            }

            private void showUpdateDialog() {
                new AlertDialog.Builder(this)
                    .setTitle("GitHub update")
                    .setMessage("App v1.0.6 previews the v1.0.4 model package. Open GitHub to get the newest APK, source, or printable model files.")
                    .setPositiveButton("Latest", (dialog, which) -> open(LATEST_RELEASE_URL))
                    .setNeutralButton("This app", (dialog, which) -> open(APP_RELEASE_URL))
                    .setNegativeButton("Close", null)
                    .show();
            }

            private void showShells() {
                List<PreviewItem> items = new ArrayList<>();
                for (String id : new String[] {"a_control_shell", "center_turbine_shell", "coal_tender_shell"}) {
                    CatalogItem item = catalog.byId.get(id);
                    if (item == null) continue;
                    float[] offset = catalog.shellOffsets.containsKey(id) ? catalog.shellOffsets.get(id) : new float[] {0f, 0f, 0f};
                    items.add(new PreviewItem(item, offset));
                }
                if (items.isEmpty()) {
                    info.setText("No shell preview items were found in the catalog.");
                    return;
                }
                title.setText("UP #80 - three shell preview");
                info.setText("Default view: A/control shell, center turbine shell, and tender shell. Drag to rotate; pinch to zoom.");
                preview.setPreviewItems(items);
            }

            private void showFullCatalog() {
                List<PreviewItem> items = new ArrayList<>();
                float x = 0f, y = 0f, rowHeight = 0f;
                for (CatalogItem item : catalog.parts) {
                    float width = item.mesh.boundsMax[0] - item.mesh.boundsMin[0];
                    float height = item.mesh.boundsMax[1] - item.mesh.boundsMin[1];
                    if (x + width > 520f) {
                        x = 0f;
                        y += rowHeight + 18f;
                        rowHeight = 0f;
                    }
                    items.add(new PreviewItem(item, new float[] {x + width * 0.5f, y + height * 0.5f, 0f}));
                    x += width + 14f;
                    rowHeight = Math.max(rowHeight, height);
                }
                title.setText("Full catalog preview");
                info.setText(catalog.parts.size() + " preview items. Use Open part, Open batch, or Download all for the real files on GitHub.");
                preview.setPreviewItems(items);
            }

            private void showSelected() {
                if (selected == null) return;
                title.setText(selected.label);
                updateInfo(selected);
                List<PreviewItem> items = new ArrayList<>();
                items.add(new PreviewItem(selected, new float[] {0f, 0f, 0f}));
                preview.setPreviewItems(items);
            }

            private void updateInfo(CatalogItem item) {
                if (item == null) return;
                info.setText(item.group + " | " + item.sourceTriangles + " STL triangles -> " + item.previewTriangles + " preview triangles");
            }

            private void open(String url) {
                if (url == null || url.length() == 0) {
                    Toast.makeText(this, "No link for this item", Toast.LENGTH_SHORT).show();
                    return;
                }
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
            }
        }
    """)


def write_docs(catalog: dict) -> None:
    total_parts = len(catalog["parts"])
    shell_parts = len([p for p in catalog["parts"] if p["group"] == "Shells"])
    chassis_parts = len([p for p in catalog["parts"] if p["group"].startswith("Chassis")])
    write_text(ROOT / "README.md", f"""
        # UP #80 Android Catalog v1.0.6

        This release fixes a launch-crash risk by removing newer Android system-insets API calls while keeping the tiny in-app GitHub update button.

        The app previews lightweight mesh data for the full v1.0.4 kit and opens GitHub links for selected parts, selected batches, the v1.0.4 manufacturing release, and the full v1.0.4 zip.

        ## Catalog Counts
        - Total preview items: {total_parts}
        - Shells: {shell_parts}
        - Chassis parts: {chassis_parts}
        - Details/test items: {total_parts - shell_parts - chassis_parts}

        ## App Behavior
        - Small `!` button opens a native update popup with GitHub release links.
        - Startup uses only legacy immersive flags for wider Android compatibility.
        - Spinner setup now uses the standard collapsed and dropdown layouts.
        - Default view shows the three shell units.
        - Full catalog view lays out every preview item.
        - Part selector previews one selected item.
        - Open part opens the raw GitHub file for that item.
        - Open batch opens the GitHub folder for that item's batch.
        - Download all opens the v1.0.4 manufacturing zip.
        - Android system navigation uses immersive mode; swipe from the edge to temporarily reveal phone Back/Home/Recents.

        ## Build Status
        This machine did not have Android SDK/Gradle installed, so no local APK was produced. The repo includes an Android Studio/Gradle project and a GitHub Actions workflow intended to build a debug APK from tag v1.0.6.
    """)
    write_text(ROOT / "BUILD_NOTES.md", """
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
    """)
    write_text(ROOT / "RELEASE_NOTES.md", """
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
    """)
    manifest = {
        "project": "UP #80 Android Catalog",
        "version": APP_VERSION,
        "sourceVersion": SOURCE_VERSION,
        "generatedUtc": catalog["generatedUtc"],
        "package": PACKAGE,
        "totalParts": total_parts,
        "shellParts": shell_parts,
        "chassisParts": chassis_parts,
        "fullManufacturingZip": FULL_ZIP,
        "appProject": "app-project",
        "apkBuiltLocally": False,
    }
    (ROOT / "app_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_workflow() -> None:
    workflow = REPO_ROOT / ".github" / "workflows" / "up80-android-v106.yml"
    write_text(workflow, """
        name: Build UP80 Android v1.0.6

        on:
          push:
            tags:
              - 'v1.0.6'
          workflow_dispatch:

        permissions:
          contents: write

        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: actions/setup-java@v4
                with:
                  distribution: temurin
                  java-version: '17'
              - uses: gradle/actions/setup-gradle@v4
              - name: Build debug APK
                run: gradle -p models/up-80-coal-turbine/v1.0.6-android-app/app-project :app:assembleDebug
              - name: Copy APK
                run: |
                  mkdir -p dist
                  cp models/up-80-coal-turbine/v1.0.6-android-app/app-project/app/build/outputs/apk/debug/app-debug.apk dist/up80-catalog-v1.0.6-debug.apk
              - name: Upload APK to release
                uses: softprops/action-gh-release@v2
                if: startsWith(github.ref, 'refs/tags/')
                with:
                  tag_name: v1.0.6
                  name: v1.0.6 Android Startup Fix
                  files: dist/up80-catalog-v1.0.6-debug.apk
                  make_latest: true
    """)


def write_release_zip() -> Path:
    release = ensure(ROOT / "release")
    zip_path = release / "up80-android-app-v1.0.6-source.zip"
    if zip_path.exists():
        zip_path = release / f"up80-android-app-v1.0.6-source-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.zip"
    include_roots = ["app-project", "source"]
    include_files = ["README.md", "BUILD_NOTES.md", "RELEASE_NOTES.md", "app_manifest.json"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in include_files:
            z.write(ROOT / rel, rel)
        for rel_root in include_roots:
            for path in sorted((ROOT / rel_root).rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(ROOT))
    return zip_path


def build() -> None:
    clean()
    parts = gather_parts()
    catalog = build_catalog(parts)
    write_project(catalog)
    write_docs(catalog)
    write_workflow()
    zip_path = write_release_zip()
    manifest = json.loads((ROOT / "app_manifest.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "root": str(ROOT),
        "version": APP_VERSION,
        "sourceVersion": SOURCE_VERSION,
        "totalParts": manifest["totalParts"],
        "shellParts": manifest["shellParts"],
        "chassisParts": manifest["chassisParts"],
        "catalogAssetBytes": (ROOT / "app-project" / "app" / "src" / "main" / "assets" / "catalog.json").stat().st_size,
        "zip": str(zip_path),
        "zipSize": zip_path.stat().st_size,
        "apkBuiltLocally": False,
    }, indent=2))


if __name__ == "__main__":
    build()
