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
