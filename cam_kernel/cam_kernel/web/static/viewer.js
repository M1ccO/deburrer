import * as THREE from './vendor/three.module.min.js';
import { OrbitControls } from './vendor/OrbitControls.js';

let scene, camera, renderer, controls;
let partGroup, toolGroup, modelGroup;
let workpieceMesh = null;
let standaloneModel = null;
let wirePolylines = [];
let vertexMarkers = [];
let vectorLines = [];
let toolAxisArrow = null;
let trailLine = null;
let cutCylinders = [];
let payloadData = null;
let currentPoseIndex = 0;
let animationId = null;

const loadingEl = document.getElementById('viewer-loading');
const errorEl = document.getElementById('viewer-error');
const legendEl = document.getElementById('viewer-legend');
const canvas = document.getElementById('viewer-canvas');

function showError(msg) {
  loadingEl.style.display = 'none';
  errorEl.textContent = msg;
  errorEl.style.display = 'block';
  canvas.style.display = 'none';
}

function initScene() {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, canvas });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(canvas.parentElement.clientWidth, canvas.parentElement.clientHeight);
  renderer.setClearColor(0x111417);

  scene = new THREE.Scene();
  scene.background = new THREE.Color('#111417');

  camera = new THREE.PerspectiveCamera(45, canvas.parentElement.clientWidth / canvas.parentElement.clientHeight, 0.5, 10000);
  camera.position.set(50, 40, 120);
  camera.up.set(0, 0, 1);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.target.set(0, 0, 0);
  controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.PAN };

  const ambient = new THREE.AmbientLight(0x666666, 0.5);
  scene.add(ambient);
  const key = new THREE.DirectionalLight(0xffffee, 1.2);
  key.position.set(1, 1, 2);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x8899cc, 0.4);
  fill.position.set(-1, -0.5, -0.5);
  scene.add(fill);

  const grid = new THREE.GridHelper(200, 20, '#2c3138', '#1a1d21');
  grid.position.z = -30;
  scene.add(grid);

  partGroup = new THREE.Group();
  partGroup.name = 'partGroup';
  scene.add(partGroup);

  modelGroup = new THREE.Group();
  modelGroup.name = 'modelGroup';
  scene.add(modelGroup);

  toolGroup = new THREE.Group();
  toolGroup.name = 'toolGroup';
  scene.add(toolGroup);

  window.addEventListener('resize', onResize);

  canvas.style.display = 'block';
  loadingEl.style.display = 'none';
  legendEl.style.display = 'flex';
  animate();
}

function onResize() {
  const w = canvas.parentElement.clientWidth;
  const h = canvas.parentElement.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}

function animate() {
  animationId = requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

function clearAll() {
  if (partGroup) {
    for (const c of [...partGroup.children]) partGroup.remove(c);
  }
  if (toolGroup) {
    for (const c of [...toolGroup.children]) toolGroup.remove(c);
  }
  wirePolylines = [];
  vertexMarkers = [];
  vectorLines = [];
  toolAxisArrow = null;
  trailLine = null;
  cutCylinders = [];
  workpieceMesh = null;
  currentPoseIndex = 0;
}

function clearModel() {
  if (modelGroup) {
    for (const c of [...modelGroup.children]) modelGroup.remove(c);
  }
  standaloneModel = null;
}

function loadModelMesh(data) {
  if (!modelGroup) return;
  clearModel();
  if (!data || !data.vertices || !data.indices) return;

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(data.vertices, 3));
  geo.setIndex(data.indices);
  geo.computeVertexNormals();

  const mat = new THREE.MeshPhongMaterial({
    color: '#526474',
    specular: '#222222',
    shininess: 25,
    flatShading: true,
  });
  standaloneModel = new THREE.Mesh(geo, mat);
  modelGroup.add(standaloneModel);

  geo.computeBoundingBox();
  const box = geo.boundingBox;
  const cx = (box.min.x + box.max.x) * 0.5;
  const cy = (box.min.y + box.max.y) * 0.5;
  const cz = (box.min.z + box.max.z) * 0.5;
  controls.target.set(cx, cy, cz);
  const span = Math.max(
    box.max.x - box.min.x,
    box.max.y - box.min.y,
    box.max.z - box.min.z
  );
  const dist = Math.max(30, span * 2.0);
  camera.position.set(cx + dist * 0.6, cy - dist * 0.5, cz + dist * 0.6);
  controls.update();

  canvas.style.display = 'block';
  loadingEl.style.display = 'none';
  legendEl.style.display = 'flex';
  errorEl.style.display = 'none';
}

function loadPreviewPayload(d) {
  try {
    clearAll();
    if (!d) { showError('Payload is empty'); return; }
    payloadData = d;

    if (d.bounds) {
      const lo = d.bounds[0], hi = d.bounds[1];
      const cx = (lo[0] + hi[0]) * 0.5;
      const cy = (lo[1] + hi[1]) * 0.5;
      const cz = (lo[2] + hi[2]) * 0.5;
      controls.target.set(cx, cy, cz);
      const span = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]);
      const dist = Math.max(30, span * 2.0);
      camera.position.set(cx + dist * 0.6, cy - dist * 0.5, cz + dist * 0.6);
      controls.update();
    }

    if (d.workpiece) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(d.workpiece.positions, 3));
      geo.setAttribute('normal', new THREE.Float32BufferAttribute(d.workpiece.normals, 3));
      geo.computeVertexNormals();
      const mat = new THREE.MeshPhongMaterial({
        color: '#526474', specular: '#222222', shininess: 25, flatShading: true,
      });
      workpieceMesh = new THREE.Mesh(geo, mat);
      partGroup.add(workpieceMesh);
      buildCutCylinders(d);
    }

    for (const poly of d.polylines) {
      if (!poly.points || poly.points.length < 2) continue;
      const pts = poly.points.map(p => new THREE.Vector3(p[0], p[1], p[2]));
      const geo = new THREE.BufferGeometry().setFromPoints(pts);
      const mat = poly.dashed
        ? new THREE.LineDashedMaterial({ color: poly.color, dashSize: 2, gapSize: 1.5 })
        : new THREE.LineBasicMaterial({ color: poly.color });
      const line = new THREE.Line(geo, mat);
      if (poly.dashed) line.computeLineDistances();
      partGroup.add(line);
      wirePolylines.push(line);
    }

    for (const m of d.markers) {
      const g = new THREE.SphereGeometry(0.5, 8, 8);
      const marker = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: m.color }));
      marker.position.set(m.position[0], m.position[1], m.position[2]);
      partGroup.add(marker);
      vertexMarkers.push(marker);
    }

    for (const v of d.vectors) {
      const start = new THREE.Vector3(v.start[0], v.start[1], v.start[2]);
      const end = new THREE.Vector3(v.end[0], v.end[1], v.end[2]);
      const dir = new THREE.Vector3().subVectors(end, start);
      const len = dir.length();
      if (len < 1e-9) continue;
      const arrow = new THREE.ArrowHelper(dir.normalize(), start, len, v.color, 0.4, 0.2);
      partGroup.add(arrow);
      vectorLines.push(arrow);
    }

    buildTool(d.tool);

    if (d.toolPoses && d.toolPoses.length > 0) {
      currentPoseIndex = 0;
      applyPose(d.toolPoses[0]);
      updateSlider();
    }
  } catch (ex) {
    showError('Payload error: ' + ex.message);
    console.error(ex);
  }
}

function buildTool(t) {
  if (!t) return;
  const radius = Math.max(0.05, t.diameter * 0.5);
  const stickout = Math.max(0.1, t.stickout);
  const cmat = new THREE.MeshPhongMaterial({ color: '#c58b3b', specular: '#333333', shininess: 40 });

  if (t.kind === 'ball') {
    const ball = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), cmat);
    ball.position.z = 0;
    toolGroup.add(ball);
    if (stickout > radius) {
      const sl = stickout - radius;
      const sh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, sl, 24), cmat);
      sh.rotation.x = Math.PI / 2;
      sh.position.z = radius + sl * 0.5;
      toolGroup.add(sh);
    }
    const contact = new THREE.Mesh(
      new THREE.SphereGeometry(Math.max(0.5, radius * 0.4), 12, 8),
      new THREE.MeshBasicMaterial({ color: '#ffd23f' })
    );
    contact.position.z = 0;
    toolGroup.add(contact);
  } else {
    const tf = Math.max(0, (t.tipFlatDiameter || 0) * 0.5);
    const ha = THREE.MathUtils.degToRad(Math.max(1, Math.min(179, t.includedAngleDeg || 90)) * 0.5);
    const cl = (radius - tf) / Math.max(1e-9, Math.tan(ha));
    const acl = Math.min(cl, stickout);
    const tr = tf + acl * Math.tan(ha);
    if (tf > 1e-6) {
      const tip = new THREE.Mesh(new THREE.CylinderGeometry(tf, tf, 0.02, 16), cmat);
      tip.rotation.x = Math.PI / 2;
      tip.position.z = 0.01;
      toolGroup.add(tip);
    }
    if (acl > 0.01) {
      const cone = new THREE.Mesh(new THREE.CylinderGeometry(tr, tf, acl, 24), cmat);
      cone.rotation.x = Math.PI / 2;
      cone.position.z = acl * 0.5;
      toolGroup.add(cone);
    }
    if (stickout > acl) {
      const sl = stickout - acl;
      const sh = new THREE.Mesh(new THREE.CylinderGeometry(tr, tr, sl, 24), cmat);
      sh.rotation.x = Math.PI / 2;
      sh.position.z = acl + sl * 0.5;
      toolGroup.add(sh);
    }
  }

  const axlen = stickout + Math.max(2, t.diameter);
  toolAxisArrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, 0), axlen, '#b58cff', 0.6, 0.3);
  toolGroup.add(toolAxisArrow);
}

function buildCutCylinders(d) {
  const cutPoly = d.polylines.find(p => p.name === 'Cutter reference');
  if (!cutPoly || !cutPoly.points || cutPoly.points.length < 2) return;
  const toolRadius = d.tool ? Math.max(0.05, d.tool.diameter * 0.5) : 3;
  const tubeMat = new THREE.MeshPhongMaterial({
    color: '#ff4d4d',
    opacity: 0.25,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const upY = new THREE.Vector3(0, 1, 0);
  for (let i = 0; i < cutPoly.points.length - 1; i++) {
    const p1 = cutPoly.points[i];
    const p2 = cutPoly.points[i + 1];
    const start = new THREE.Vector3(p1[0], p1[1], p1[2]);
    const end = new THREE.Vector3(p2[0], p2[1], p2[2]);
    const dir = new THREE.Vector3().subVectors(end, start);
    const length = dir.length();
    if (length < 1e-6) continue;
    const cylGeo = new THREE.CylinderGeometry(toolRadius, toolRadius, length, 12);
    const cyl = new THREE.Mesh(cylGeo, tubeMat);
    const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
    cyl.position.copy(mid);
    cyl.quaternion.setFromUnitVectors(upY, dir.normalize());
    cyl.renderOrder = 2;
    partGroup.add(cyl);
    cutCylinders.push(cyl);
  }
}

function applyPose(pose) {
  if (!toolGroup || !partGroup) return;
  const ref = new THREE.Vector3(pose.cutterReference[0], pose.cutterReference[1], pose.cutterReference[2]);
  const axisSrc = pose.toolAxis;
  const axis = new THREE.Vector3(axisSrc[0], axisSrc[1], axisSrc[2]).normalize();
  if (payloadData) {
    const sa = new THREE.Vector3(payloadData.spindle.axis[0], payloadData.spindle.axis[1], payloadData.spindle.axis[2]).normalize();
    const rotAngle = THREE.MathUtils.degToRad(pose.partRotationDeg);
    const rotQuat = new THREE.Quaternion().setFromAxisAngle(sa, rotAngle);
    ref.applyQuaternion(rotQuat);
    partGroup.setRotationFromQuaternion(rotQuat);
  }
  toolGroup.position.copy(ref);
  toolGroup.setRotationFromQuaternion(
    new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), axis)
  );
}

function updateTrail(index) {
  if (trailLine) { toolGroup.remove(trailLine); trailLine = null; }
  if (!payloadData || !payloadData.toolPoses) return;
  const poses = payloadData.toolPoses;
  const last = Math.min(index, poses.length - 1);
  if (last <= 0) return;
  const pts = [];
  for (let i = 0; i <= last; i++) {
    const p = poses[i].cutterReference;
    pts.push(new THREE.Vector3(p[0], p[1], p[2]));
  }
  trailLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({ color: '#ff9f43' })
  );
  trailLine.renderOrder = 1;
  trailLine.material.depthTest = false;
  toolGroup.add(trailLine);
}

function setPoseIndex(index) {
  if (!payloadData || !payloadData.toolPoses) return;
  currentPoseIndex = Math.max(0, Math.min(index, payloadData.toolPoses.length - 1));
  applyPose(payloadData.toolPoses[currentPoseIndex]);
  updateTrail(currentPoseIndex);
  document.getElementById('pose-slider').value = currentPoseIndex;
  document.getElementById('pose-label').textContent = `${currentPoseIndex + 1}/${payloadData.toolPoses.length}`;
}

function stepPose(delta) {
  setPoseIndex(currentPoseIndex + delta);
}

function seekPose(value) {
  setPoseIndex(parseInt(value));
}

function updateSlider() {
  const controls = document.getElementById('time-controls');
  const slider = document.getElementById('pose-slider');
  const label = document.getElementById('pose-label');
  if (!payloadData || !payloadData.toolPoses || payloadData.toolPoses.length <= 1) {
    controls.style.display = 'none';
    return;
  }
  slider.max = payloadData.toolPoses.length - 1;
  slider.value = 0;
  label.textContent = `1/${payloadData.toolPoses.length}`;
  controls.style.display = 'flex';
}

initScene();

window.loadPreviewPayload = loadPreviewPayload;
window.loadModelMesh = loadModelMesh;
window.viewerStep = stepPose;
window.viewerSeek = seekPose;
