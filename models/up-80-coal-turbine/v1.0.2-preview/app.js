(() => {
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
})();