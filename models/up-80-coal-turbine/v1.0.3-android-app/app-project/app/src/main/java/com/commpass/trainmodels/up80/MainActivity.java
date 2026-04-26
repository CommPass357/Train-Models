package com.commpass.trainmodels.up80;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
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
    private CatalogData catalog;
    private MeshPreviewView preview;
    private Spinner spinner;
    private TextView title;
    private TextView info;
    private CatalogItem selected;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
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
        root.setPadding(12, 12, 12, 12);

        title = new TextView(this);
        title.setText("UP #80 Catalog v1.0.3");
        title.setTextSize(20);
        title.setPadding(0, 0, 0, 8);
        root.addView(title);

        preview = new MeshPreviewView(this);
        root.addView(preview, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));

        spinner = new Spinner(this);
        ArrayAdapter<CatalogItem> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, catalog.parts);
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
        row3.addView(button("v1.0.1 release", v -> open(catalog.manufacturingReleaseUrl)));
        row3.addView(button("Chassis docs", v -> open(catalog.chassisPartsDocUrl)));
        root.addView(row3);

        setContentView(root);
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

    private void showShells() {
        List<PreviewItem> items = new ArrayList<>();
        for (String id : new String[] {"a_control_shell", "center_turbine_shell", "coal_tender_shell"}) {
            float[] offset = catalog.shellOffsets.containsKey(id) ? catalog.shellOffsets.get(id) : new float[] {0f, 0f, 0f};
            items.add(new PreviewItem(catalog.byId.get(id), offset));
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
