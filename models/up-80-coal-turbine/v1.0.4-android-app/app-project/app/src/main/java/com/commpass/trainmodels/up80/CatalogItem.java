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
