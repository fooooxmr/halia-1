import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { STLLoader } from "./vendor/STLLoader.js";

const PARTS = [
  { id: "frame", file: "frame.stl", color: 0x2a5984, kind: "body", explode: [0, 0, 0] },
  { id: "tongue", file: "tongue.stl", color: 0xb7bbbf, kind: "body", explode: [-22, 0, 10] },
  { id: "blade", file: "blade.stl", color: 0xc6922e, kind: "body", explode: [0, -26, 0] },
  { id: "turret", file: "turret.stl", color: 0x1c7c80, kind: "body", explode: [0, 18, 16] },
  { id: "clip", file: "clip.stl", color: 0x9c5528, kind: "body", explode: [20, 8, 0] },
  { id: "screw-t", file: "screw_translation_M3x25.stl", color: 0xd5d8dc, kind: "screw", explode: [0, -26, 8] },
  { id: "screw-g", file: "screw_tongue_M3x10.stl", color: 0xd5d8dc, kind: "screw", explode: [-8, 0, 18] },
  { id: "screw-a", file: "screw_angle_M3x12.stl", color: 0xd5d8dc, kind: "screw", explode: [0, 18, 24] },
  { id: "screw-h", file: "screw_hinge_M3x8.stl", color: 0xd5d8dc, kind: "screw", explode: [0, 18, 22] },
  { id: "shaft", file: "bone_shaft.stl", color: 0xe8e1d0, kind: "bone", explode: [0, 0, 0] },
  { id: "head", file: "bone_head.stl", color: 0xe8e1d0, kind: "bone", explode: [0, 0, 0] },
  { id: "wire1", file: "wire1.stl", color: 0xd42722, kind: "wire", explode: [0, 0, 0] },
  { id: "wire2", file: "wire2.stl", color: 0xd42722, kind: "wire", explode: [0, 0, 0] },
];

const stage = document.getElementById("stage");
const status = document.getElementById("status");
const model = new THREE.Group();
const meshes = [];

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(0x121418, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.add(model);
scene.add(new THREE.AmbientLight(0xf3eee6, 0.72));

const key = new THREE.DirectionalLight(0xfff6ec, 3.1);
key.position.set(70, -30, 90);
scene.add(key);
const fill = new THREE.DirectionalLight(0xc9d7ea, 1.35);
fill.position.set(-60, -90, 24);
scene.add(fill);
const rim = new THREE.DirectionalLight(0xf0d7b0, 1.15);
rim.position.set(-20, 80, 16);
scene.add(rim);

const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 4000);
camera.up.set(0, 0, 1);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.rotateSpeed = 0.85;
controls.zoomSpeed = 0.8;
controls.screenSpacePanning = true;
controls.autoRotateSpeed = 0.7;

function resize() {
  const w = stage.clientWidth;
  const h = stage.clientHeight || 480;
  renderer.setSize(w, h, false);
  renderer.domElement.style.width = "100%";
  renderer.domElement.style.height = "100%";
  camera.aspect = w / Math.max(h, 1);
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage);
resize();

function materialFor(part) {
  if (part.kind === "bone") {
    return new THREE.MeshStandardMaterial({
      color: part.color,
      roughness: 0.72,
      metalness: 0.02,
      transparent: true,
      opacity: 0.4,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
  }
  if (part.kind === "wire") {
    return new THREE.MeshStandardMaterial({
      color: part.color,
      roughness: 0.32,
      metalness: 0.2,
      emissive: 0x4a100e,
      emissiveIntensity: 0.45,
      side: THREE.DoubleSide,
    });
  }
  return new THREE.MeshStandardMaterial({
    color: part.color,
    roughness: part.kind === "screw" ? 0.28 : 0.42,
    metalness: part.kind === "screw" ? 0.72 : 0.48,
    side: THREE.DoubleSide,
  });
}

function place(dir, up) {
  const box = new THREE.Box3().setFromObject(model);
  if (box.isEmpty()) return;
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const focus = sphere.center.clone();
  focus.x = THREE.MathUtils.lerp(focus.x, -4, 0.35);
  focus.y = THREE.MathUtils.lerp(focus.y, 6, 0.4);
  const dist = sphere.radius / Math.sin(THREE.MathUtils.degToRad(camera.fov * 0.5)) * 0.72;
  camera.up.copy(up);
  camera.position.copy(focus).add(dir.clone().normalize().multiplyScalar(dist));
  controls.target.copy(focus);
  controls.minDistance = sphere.radius * 0.28;
  controls.maxDistance = sphere.radius * 8;
  controls.update();
}

const VIEWS = {
  home: [new THREE.Vector3(0.72, -0.82, 0.72), new THREE.Vector3(0, 0, 1)],
  top: [new THREE.Vector3(0.04, -0.12, 1), new THREE.Vector3(0, 1, 0)],
  side: [new THREE.Vector3(0.2, -1, 0.22), new THREE.Vector3(0, 0, 1)],
  end: [new THREE.Vector3(1, 0.05, 0.28), new THREE.Vector3(0, 0, 1)],
};

function show(name) {
  const [dir, up] = VIEWS[name];
  place(dir, up);
}

function setExplode(t) {
  for (const mesh of meshes) {
    const o = mesh.userData.explode;
    mesh.position.set(o[0] * t, o[1] * t, o[2] * t);
  }
}

function setKind(kind, visible) {
  for (const mesh of meshes) {
    if (mesh.userData.kind === kind) mesh.visible = visible;
  }
}

let done = 0;
let failed = 0;

function finishOne() {
  done += 1;
  status.textContent = failed
    ? `загружено ${done - failed} из ${PARTS.length}, ошибок ${failed}`
    : `читаю модель  ${done} / ${PARTS.length}`;
  if (done === PARTS.length && done - failed > 0) {
    status.textContent = "тяните, чтобы вращать";
    show("home");
    window.__haliaReady = true;
  }
}

for (const part of PARTS) {
  const url = new URL(`export/viz/${part.file}`, document.baseURI).href;
  new STLLoader().load(url, (geom) => {
    geom.computeVertexNormals();
    const mesh = new THREE.Mesh(geom, materialFor(part));
    mesh.userData.explode = part.explode;
    mesh.userData.kind = part.kind;
    mesh.name = part.id;
    model.add(mesh);
    meshes.push(mesh);
    finishOne();
  }, undefined, () => {
    failed += 1;
    finishOne();
  });
}

function tick() {
  requestAnimationFrame(tick);
  controls.update();
  renderer.render(scene, camera);
}
tick();

function bindPress(id, fn) {
  const el = document.getElementById(id);
  el.addEventListener("click", () => fn(el));
}

bindPress("view-home", () => show("home"));
bindPress("view-top", () => show("top"));
bindPress("view-side", () => show("side"));
bindPress("view-end", () => show("end"));
bindPress("view-spin", (el) => {
  const on = el.getAttribute("aria-pressed") !== "true";
  el.setAttribute("aria-pressed", on ? "true" : "false");
  controls.autoRotate = on;
});

for (const [id, kind] of [["tog-bone", "bone"], ["tog-wire", "wire"], ["tog-screw", "screw"]]) {
  bindPress(id, (el) => {
    const next = el.getAttribute("aria-pressed") !== "true";
    el.setAttribute("aria-pressed", next ? "true" : "false");
    setKind(kind, next);
  });
}

document.getElementById("explode").addEventListener("input", (e) => {
  setExplode(Number(e.target.value));
});

stage.addEventListener("dblclick", () => show("home"));

window.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea, a")) return;
  if (e.key === "1") show("home");
  if (e.key === "2") show("top");
  if (e.key === "3") show("side");
  if (e.key === "4") show("end");
});

const sections = [...document.querySelectorAll(".prose section[id], #model")];
const links = [...document.querySelectorAll(".rail a")];
if ("IntersectionObserver" in window) {
  const io = new IntersectionObserver((entries) => {
    const visible = entries.filter((en) => en.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    for (const link of links) {
      link.classList.toggle("here", link.getAttribute("href") === `#${visible.target.id}`);
    }
  }, { rootMargin: "-20% 0px -55% 0px", threshold: [0.15, 0.4] });
  sections.forEach((s) => io.observe(s));
}
