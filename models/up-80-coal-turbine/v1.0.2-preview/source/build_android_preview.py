from __future__ import annotations

import json
import math
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT.parent
SOURCE_VERSION = "v1.0.1"
SOURCE_ROOT = MODEL_ROOT / SOURCE_VERSION
RELEASE_NAME = "up80-android-preview-v1.0.2.zip"


def clean() -> None:
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "release").mkdir(parents=True, exist_ok=True)


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


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def normalize(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length < 1e-9:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def bounds_for_positions(positions: list[float]) -> dict:
    xs = positions[0::3]
    ys = positions[1::3]
    zs = positions[2::3]
    mn = [min(xs), min(ys), min(zs)]
    mx = [max(xs), max(ys), max(zs)]
    return {"min": mn, "max": mx, "size": [mx[i] - mn[i] for i in range(3)], "center": [(mn[i] + mx[i]) / 2 for i in range(3)]}


def simplified_mesh(path: Path, max_triangles: int) -> dict:
    triangles = parse_ascii_stl(path)
    if not triangles:
        raise ValueError(f"No triangles found in {path}")
    step = max(1, math.ceil(len(triangles) / max_triangles))
    sampled = triangles[::step][:max_triangles]
    positions: list[float] = []
    normals: list[float] = []
    for tri in sampled:
        n = normalize(cross(sub(tri[1], tri[0]), sub(tri[2], tri[0])))
        for vertex in tri:
            positions.extend(round(coord, 3) for coord in vertex)
            normals.extend(round(coord, 4) for coord in n)
    return {
        "positions": positions,
        "normals": normals,
        "sourceTriangles": len(triangles),
        "previewTriangles": len(sampled),
        "bounds": bounds_for_positions(positions),
    }


def label_from_stem(stem: str) -> str:
    words = stem.replace("up80_", "").replace("_", " ").split()
    return " ".join(word.upper() if word in {"a"} else word.capitalize() for word in words)


def gather_parts() -> list[dict]:
    validation = json.loads((SOURCE_ROOT / "validation_report.json").read_text(encoding="utf-8"))
    parts = []
    order = 0
    for rel in validation["shell_stl_files"]:
        path = SOURCE_ROOT / rel
        unit = path.stem.replace("_shell", "")
        parts.append({
            "id": path.stem,
            "label": label_from_stem(path.stem),
            "group": "Shells",
            "unit": unit,
            "source": f"../{SOURCE_VERSION}/{rel}",
            "path": path,
            "order": order,
            "max_triangles": 2200,
            "color": {"a_control": "#f6c54d", "center_turbine": "#d1d6d0", "coal_tender": "#2b2d30"}.get(unit, "#d8d8d8"),
        })
        order += 1
    for unit, rels in validation["chassis_part_index"].items():
        for rel in rels:
            path = SOURCE_ROOT / rel
            parts.append({
                "id": path.stem,
                "label": label_from_stem(path.stem),
                "group": f"Chassis - {label_from_stem(unit)}",
                "unit": unit,
                "source": f"../{SOURCE_VERSION}/{rel}",
                "path": path,
                "order": order,
                "max_triangles": 450 if "base_plate" not in path.stem and "sideframes" not in path.stem else 900,
                "color": {"a_control": "#4f6f8f", "center_turbine": "#6f777f", "coal_tender": "#5f5142"}.get(unit, "#686868"),
            })
            order += 1
    for rel in ["exports/stl/details/up80_detail_sprue.stl", "exports/stl/details/up80_test_coupons.stl"]:
        path = SOURCE_ROOT / rel
        parts.append({
            "id": path.stem,
            "label": label_from_stem(path.stem),
            "group": "Details",
            "unit": "details",
            "source": f"../{SOURCE_VERSION}/{rel}",
            "path": path,
            "order": order,
            "max_triangles": 1100,
            "color": "#b08c5a",
        })
        order += 1
    return parts


def shell_consist_offsets(meshes: dict[str, dict]) -> dict[str, list[float]]:
    ids = ["a_control_shell", "center_turbine_shell", "coal_tender_shell"]
    gap = 8.0
    lengths = [meshes[i]["bounds"]["size"][0] for i in ids]
    center_x = 0.0
    a_x = center_x - lengths[1] / 2 - gap - lengths[0] / 2
    tender_x = center_x + lengths[1] / 2 + gap + lengths[2] / 2
    return {
        "a_control_shell": [round(a_x, 3), 0, 0],
        "center_turbine_shell": [0, 0, 0],
        "coal_tender_shell": [round(tender_x, 3), 0, 0],
    }


def build_data(parts: list[dict]) -> dict:
    meshes = {}
    manifest_parts = []
    for part in parts:
        mesh = simplified_mesh(part["path"], part["max_triangles"])
        mesh["color"] = part["color"]
        meshes[part["id"]] = mesh
        manifest_parts.append({
            "id": part["id"],
            "label": part["label"],
            "group": part["group"],
            "unit": part["unit"],
            "source": part["source"],
            "sourceTriangles": mesh["sourceTriangles"],
            "previewTriangles": mesh["previewTriangles"],
            "bounds": mesh["bounds"],
            "color": part["color"],
            "order": part["order"],
        })
    data = {
        "project": "HO Union Pacific #80 Coal Turbine Android Preview",
        "version": "v1.0.2",
        "sourceVersion": SOURCE_VERSION,
        "generatedUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "defaultView": ["a_control_shell", "center_turbine_shell", "coal_tender_shell"],
        "shellConsistOffsets": shell_consist_offsets(meshes),
        "links": {
            "manufacturingRelease": "https://github.com/CommPass357/Train-Models/releases/tag/v1.0.1",
            "manufacturingZip": "https://github.com/CommPass357/Train-Models/releases/download/v1.0.1/up-80-coal-turbine-ho-v1.0.1.zip",
            "chassisPartsDoc": "https://github.com/CommPass357/Train-Models/blob/main/models/up-80-coal-turbine/v1.0.1/docs/CHASSIS_PARTS.md",
        },
        "parts": manifest_parts,
        "meshes": meshes,
    }
    return data


def write_index() -> None:
    (ROOT / "index.html").write_text("""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>UP #80 Android Preview v1.0.2</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main class="app-shell">
    <section class="viewer-wrap">
      <canvas id="viewer" aria-label="3D preview canvas"></canvas>
      <div class="hud">
        <div id="viewTitle">Three Shell Consist</div>
        <div id="viewMeta">drag rotate | pinch zoom</div>
      </div>
    </section>
    <section class="controls">
      <div class="button-row">
        <button id="shellsBtn" type="button">3 Shells</button>
        <button id="fullKitBtn" type="button">Full Kit</button>
        <button id="resetBtn" type="button">Reset</button>
        <button id="bgBtn" type="button">Background</button>
      </div>
      <label class="part-label" for="partSelect">Part preview</label>
      <select id="partSelect"></select>
      <div id="partInfo" class="part-info"></div>
      <details>
        <summary>Android notes</summary>
        <p>This viewer uses simplified preview meshes from v1.0.1. Use the v1.0.1 release for printable STL, STEP, DXF, and build documents.</p>
      </details>
    </section>
  </main>
  <script src="data/preview_meshes.js"></script>
  <script src="app.js"></script>
</body>
</html>
""", encoding="utf-8")


def write_style() -> None:
    (ROOT / "style.css").write_text("""* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; background: #121416; color: #f4f1e8; font-family: system-ui, -apple-system, Segoe UI, sans-serif; }
body { overflow: hidden; }
.app-shell { min-height: 100svh; display: grid; grid-template-rows: 1fr auto; }
.viewer-wrap { position: relative; min-height: 62svh; background: #111418; touch-action: none; }
#viewer { display: block; width: 100%; height: 100%; min-height: 62svh; }
.hud { position: absolute; left: 12px; right: 12px; top: 12px; display: flex; justify-content: space-between; gap: 12px; color: #f7f0df; text-shadow: 0 1px 3px #000; font-size: 13px; pointer-events: none; }
#viewTitle { font-weight: 700; }
#viewMeta { opacity: 0.78; text-align: right; }
.controls { padding: 10px 12px calc(12px + env(safe-area-inset-bottom)); background: #202326; border-top: 1px solid #383d42; }
.button-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
button, select { width: 100%; min-height: 42px; border: 1px solid #4a5056; border-radius: 8px; background: #2c3136; color: #f4f1e8; font: inherit; }
button:active { transform: translateY(1px); background: #3a4148; }
.part-label { display: block; margin: 4px 0 6px; color: #c9c5bb; font-size: 12px; }
select { padding: 0 10px; }
.part-info { min-height: 36px; margin-top: 8px; color: #d5d1c8; font-size: 12px; line-height: 1.35; }
details { margin-top: 8px; color: #d5d1c8; font-size: 12px; }
summary { cursor: pointer; }
@media (orientation: landscape) {
  .app-shell { grid-template-columns: 1fr 360px; grid-template-rows: 1fr; }
  .viewer-wrap, #viewer { min-height: 100svh; }
  .controls { border-top: 0; border-left: 1px solid #383d42; overflow: auto; }
  .button-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
""", encoding="utf-8")


def write_app() -> None:
    (ROOT / "app.js").write_text(r"""(() => {
  const DATA = window.UP80_PREVIEW_DATA;
  const canvas = document.getElementById('viewer');
  const gl = canvas.getContext('webgl', { antialias: true, alpha: false });
  const title = document.getElementById('viewTitle');
  const meta = document.getElementById('viewMeta');
  const select = document.getElementById('partSelect');
  const info = document.getElementById('partInfo');
  const bgColors = ['#111418', '#f1eee5', '#18202a'];
  let bgIndex = 0;
  let rotationX = -0.55;
  let rotationY = 0.72;
  let zoom = 1.0;
  let pan = [0, 0, 0];
  let activeItems = [];
  const buffers = new Map();
  const pointerState = { pointers: new Map(), lastDist: 0 };

  if (!gl) {
    document.body.innerHTML = '<p style="padding:16px">This phone browser does not support WebGL. Try Android Chrome or Edge.</p>';
    return;
  }

  const vs = `
    attribute vec3 aPosition;
    attribute vec3 aNormal;
    uniform mat4 uMatrix;
    uniform mat3 uNormalMatrix;
    uniform vec3 uOffset;
    varying vec3 vNormal;
    varying vec3 vPosition;
    void main() {
      vec3 p = aPosition + uOffset;
      vNormal = normalize(uNormalMatrix * aNormal);
      vPosition = p;
      gl_Position = uMatrix * vec4(p, 1.0);
    }`;
  const fs = `
    precision mediump float;
    uniform vec3 uColor;
    varying vec3 vNormal;
    varying vec3 vPosition;
    void main() {
      vec3 light = normalize(vec3(0.35, 0.65, 0.8));
      float diffuse = max(dot(normalize(vNormal), light), 0.0);
      float rim = 0.18 + 0.20 * max(dot(normalize(vNormal), normalize(vec3(-0.5, -0.2, 0.8))), 0.0);
      vec3 color = uColor * (0.38 + diffuse * 0.72 + rim);
      gl_FragColor = vec4(color, 1.0);
    }`;

  function shader(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }

  const program = gl.createProgram();
  gl.attachShader(program, shader(gl.VERTEX_SHADER, vs));
  gl.attachShader(program, shader(gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);

  const loc = {
    pos: gl.getAttribLocation(program, 'aPosition'),
    normal: gl.getAttribLocation(program, 'aNormal'),
    matrix: gl.getUniformLocation(program, 'uMatrix'),
    normalMatrix: gl.getUniformLocation(program, 'uNormalMatrix'),
    color: gl.getUniformLocation(program, 'uColor'),
    offset: gl.getUniformLocation(program, 'uOffset')
  };

  function hexColor(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }

  function bufferFor(id) {
    if (buffers.has(id)) return buffers.get(id);
    const mesh = DATA.meshes[id];
    const pos = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, pos);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(mesh.positions), gl.STATIC_DRAW);
    const normal = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, normal);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(mesh.normals), gl.STATIC_DRAW);
    const out = { pos, normal, count: mesh.positions.length / 3, color: hexColor(mesh.color), bounds: mesh.bounds };
    buffers.set(id, out);
    return out;
  }

  function identity() { return [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]; }
  function multiply(a, b) {
    const out = new Array(16).fill(0);
    for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) for (let k = 0; k < 4; k++) out[c*4+r] += a[k*4+r] * b[c*4+k];
    return out;
  }
  function translate(m, x, y, z) { const t = identity(); t[12]=x; t[13]=y; t[14]=z; return multiply(m, t); }
  function scale(m, s) { const t = identity(); t[0]=s; t[5]=s; t[10]=s; return multiply(m, t); }
  function rotateX(m, a) { const c=Math.cos(a), s=Math.sin(a); return multiply(m, [1,0,0,0, 0,c,s,0, 0,-s,c,0, 0,0,0,1]); }
  function rotateY(m, a) { const c=Math.cos(a), s=Math.sin(a); return multiply(m, [c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,0,1]); }
  function perspective(fov, aspect, near, far) {
    const f = 1 / Math.tan(fov / 2), nf = 1 / (near - far);
    return [f/aspect,0,0,0, 0,f,0,0, 0,0,(far+near)*nf,-1, 0,0,2*far*near*nf,0];
  }
  function normalMatrix() {
    const cx=Math.cos(rotationX), sx=Math.sin(rotationX), cy=Math.cos(rotationY), sy=Math.sin(rotationY);
    return [cy, sx*sy, -cx*sy, 0, cx, sx, sy, -sx*cy, cx*cy];
  }

  function combinedBounds(items) {
    const mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
    for (const item of items) {
      const b = DATA.meshes[item.id].bounds, o = item.offset || [0,0,0];
      for (let i = 0; i < 3; i++) {
        mn[i] = Math.min(mn[i], b.min[i] + o[i]);
        mx[i] = Math.max(mx[i], b.max[i] + o[i]);
      }
    }
    return { center: mn.map((v, i) => (v + mx[i]) / 2), size: mn.map((v, i) => mx[i] - v) };
  }

  function setView(items, name) {
    activeItems = items;
    const b = combinedBounds(items);
    pan = [-b.center[0], -b.center[1], -b.center[2]];
    zoom = 170 / Math.max(...b.size, 1);
    title.textContent = name;
    meta.textContent = `${items.length} item${items.length === 1 ? '' : 's'} | drag rotate | pinch zoom`;
    if (items.length === 1) {
      const p = DATA.parts.find(x => x.id === items[0].id);
      info.textContent = `${p.group} | ${p.sourceTriangles} STL triangles -> ${p.previewTriangles} preview triangles`;
      select.value = items[0].id;
    } else {
      info.textContent = `${DATA.sourceVersion} preview geometry. Use the v1.0.1 release for printable files.`;
    }
    render();
  }

  function shellView() {
    const items = DATA.defaultView.map(id => ({ id, offset: DATA.shellConsistOffsets[id] || [0,0,0] }));
    setView(items, 'Three Shell Consist');
  }

  function fullKitView() {
    const items = [];
    let x = 0, y = 0, row = 0;
    for (const part of DATA.parts) {
      const b = DATA.meshes[part.id].bounds.size;
      if (x + b[0] > 520) { x = 0; y += row + 18; row = 0; }
      items.push({ id: part.id, offset: [x + b[0] / 2, y + b[1] / 2, 0] });
      x += b[0] + 14;
      row = Math.max(row, b[1]);
    }
    setView(items, 'Full Kit Gallery');
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.floor(canvas.clientWidth * dpr), h = Math.floor(canvas.clientHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    render();
  }

  function render() {
    if (!activeItems.length) return;
    gl.viewport(0, 0, canvas.width, canvas.height);
    const bg = hexColor(bgColors[bgIndex]);
    gl.clearColor(bg[0], bg[1], bg[2], 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    const aspect = canvas.width / Math.max(canvas.height, 1);
    let m = perspective(Math.PI / 4, aspect, 0.1, 2000);
    m = translate(m, 0, 0, -430);
    m = scale(m, zoom);
    m = rotateX(m, rotationX);
    m = rotateY(m, rotationY);
    m = translate(m, pan[0], pan[1], pan[2]);
    gl.uniformMatrix4fv(loc.matrix, false, new Float32Array(m));
    gl.uniformMatrix3fv(loc.normalMatrix, false, new Float32Array(normalMatrix()));
    for (const item of activeItems) {
      const b = bufferFor(item.id);
      gl.bindBuffer(gl.ARRAY_BUFFER, b.pos);
      gl.enableVertexAttribArray(loc.pos);
      gl.vertexAttribPointer(loc.pos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, b.normal);
      gl.enableVertexAttribArray(loc.normal);
      gl.vertexAttribPointer(loc.normal, 3, gl.FLOAT, false, 0, 0);
      gl.uniform3fv(loc.color, new Float32Array(b.color));
      gl.uniform3fv(loc.offset, new Float32Array(item.offset || [0,0,0]));
      gl.drawArrays(gl.TRIANGLES, 0, b.count);
    }
  }

  function populateSelect() {
    let group = '';
    for (const part of DATA.parts) {
      if (part.group !== group) {
        group = part.group;
        const optgroup = document.createElement('optgroup');
        optgroup.label = group;
        select.appendChild(optgroup);
      }
      const option = document.createElement('option');
      option.value = part.id;
      option.textContent = part.label;
      select.lastElementChild.appendChild(option);
    }
    select.addEventListener('change', () => setView([{ id: select.value, offset: [0,0,0] }], DATA.parts.find(p => p.id === select.value).label));
  }

  canvas.addEventListener('pointerdown', e => { canvas.setPointerCapture(e.pointerId); pointerState.pointers.set(e.pointerId, [e.clientX, e.clientY]); });
  canvas.addEventListener('pointerup', e => { pointerState.pointers.delete(e.pointerId); pointerState.lastDist = 0; });
  canvas.addEventListener('pointercancel', e => { pointerState.pointers.delete(e.pointerId); pointerState.lastDist = 0; });
  canvas.addEventListener('pointermove', e => {
    if (!pointerState.pointers.has(e.pointerId)) return;
    const prev = pointerState.pointers.get(e.pointerId);
    pointerState.pointers.set(e.pointerId, [e.clientX, e.clientY]);
    const points = [...pointerState.pointers.values()];
    if (points.length === 1) {
      rotationY += (e.clientX - prev[0]) * 0.008;
      rotationX += (e.clientY - prev[1]) * 0.008;
    } else if (points.length >= 2) {
      const d = Math.hypot(points[0][0] - points[1][0], points[0][1] - points[1][1]);
      if (pointerState.lastDist) zoom *= Math.max(0.75, Math.min(1.25, d / pointerState.lastDist));
      pointerState.lastDist = d;
    }
    render();
  });
  canvas.addEventListener('wheel', e => { e.preventDefault(); zoom *= e.deltaY > 0 ? 0.92 : 1.08; render(); }, { passive: false });
  document.getElementById('shellsBtn').addEventListener('click', shellView);
  document.getElementById('fullKitBtn').addEventListener('click', fullKitView);
  document.getElementById('resetBtn').addEventListener('click', () => { rotationX = -0.55; rotationY = 0.72; activeItems.length > 3 ? fullKitView() : shellView(); });
  document.getElementById('bgBtn').addEventListener('click', () => { bgIndex = (bgIndex + 1) % bgColors.length; canvas.parentElement.style.background = bgColors[bgIndex]; render(); });
  window.addEventListener('resize', resize);
  populateSelect();
  resize();
  shellView();
})();""", encoding="utf-8")


def write_docs(data: dict) -> None:
    part_count = len(data["parts"])
    shell_count = len([p for p in data["parts"] if p["group"] == "Shells"])
    (ROOT / "README.md").write_text(f"""# UP #80 Android Preview v1.0.2

This is a phone-friendly visual preview of the v1.0.1 HO Union Pacific #80 coal turbine kit.

Open `index.html` in Android Chrome, Edge, or Samsung Internet after extracting the zip. The default view shows the three shell units as a consist. Use the selector for the full kit gallery, including split chassis parts, detail sprue, and test coupons.

## Contents
- `index.html`: mobile WebGL viewer.
- `app.js` and `style.css`: viewer controls and layout.
- `data/preview_meshes.js`: lightweight preview mesh data generated from v1.0.1 STL files.
- `preview_manifest.json`: source files, groups, triangle counts, and release links.

## Counts
- Shell preview files: {shell_count}
- Total preview parts: {part_count}
- Source manufacturing version: v1.0.1

For printable files, use the v1.0.1 manufacturing release:
https://github.com/CommPass357/Train-Models/releases/tag/v1.0.1
""", encoding="utf-8")
    (ROOT / "RELEASE_NOTES.md").write_text("""# v1.0.2 Android Preview

Phone web preview release built from the v1.0.1 printable kit.

## Added
- Android-friendly WebGL viewer.
- Default three-shell consist preview.
- Full kit gallery for shells, split chassis parts, detail sprue, and test coupons.
- Lightweight preview mesh data and manifest.

## Notes
- This release is for visual inspection only.
- Printable STL, STEP, DXF, 3MF, BOM, and build files remain in v1.0.1.
""", encoding="utf-8")


def write_data(data: dict) -> None:
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "preview_meshes.js").write_text("window.UP80_PREVIEW_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
    manifest = {k: v for k, v in data.items() if k != "meshes"}
    manifest["meshDataFile"] = "data/preview_meshes.js"
    (ROOT / "preview_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_zip() -> Path:
    release_dir = ROOT / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    zip_path = release_dir / RELEASE_NAME
    if zip_path.exists():
        zip_path = release_dir / f"up80-android-preview-v1.0.2-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.zip"
    include = ["index.html", "app.js", "style.css", "README.md", "RELEASE_NOTES.md", "preview_manifest.json", "data/preview_meshes.js"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in include:
            z.write(ROOT / rel, rel)
    return zip_path


def build() -> None:
    clean()
    parts = gather_parts()
    data = build_data(parts)
    write_index()
    write_style()
    write_app()
    write_data(data)
    write_docs(data)
    zip_path = write_zip()
    manifest = json.loads((ROOT / "preview_manifest.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "previewRoot": str(ROOT),
        "sourceVersion": SOURCE_VERSION,
        "parts": len(manifest["parts"]),
        "shells": len([p for p in manifest["parts"] if p["group"] == "Shells"]),
        "zip": str(zip_path),
        "zipSize": zip_path.stat().st_size,
        "meshDataSize": (ROOT / "data" / "preview_meshes.js").stat().st_size,
    }, indent=2))


if __name__ == "__main__":
    build()
