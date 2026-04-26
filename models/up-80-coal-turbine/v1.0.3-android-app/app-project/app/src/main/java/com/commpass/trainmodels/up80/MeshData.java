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
