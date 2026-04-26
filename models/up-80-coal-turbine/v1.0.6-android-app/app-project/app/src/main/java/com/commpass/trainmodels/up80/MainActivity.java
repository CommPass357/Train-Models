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
