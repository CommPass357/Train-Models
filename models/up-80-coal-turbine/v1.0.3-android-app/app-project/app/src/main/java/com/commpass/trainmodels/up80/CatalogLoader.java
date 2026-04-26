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
