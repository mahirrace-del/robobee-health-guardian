import * as THREE from "./vendor/three.module.js";
import { GLTFLoader } from "./vendor/three/examples/jsm/loaders/GLTFLoader.js";
import { DRACOLoader } from "./vendor/three/examples/jsm/loaders/DRACOLoader.js";
import { MeshoptDecoder } from "./vendor/three/examples/jsm/libs/meshopt_decoder.module.js";
import { mergeVertices } from "./vendor/three/examples/jsm/utils/BufferGeometryUtils.js";

const mount = document.getElementById("body3d-canvas");
const stage = document.getElementById("body-stage");
if (!mount || !stage) throw new Error("The body explorer mount point is missing.");

const vertexShader = `
varying vec3 vNormal;
varying vec3 vViewPosition;
varying vec3 vPosition;
void main() {
  vNormal = normalize(normalMatrix * normal);
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  vViewPosition = -mvPosition.xyz;
  vPosition = position;
  gl_Position = projectionMatrix * mvPosition;
}`;
const fragmentShader = `
uniform vec3 uRim;
uniform vec3 uCore;
uniform float uTime;
uniform float uOpacity;
varying vec3 vNormal;
varying vec3 vViewPosition;
varying vec3 vPosition;
void main() {
  float edge = pow(1.0 - abs(dot(normalize(vNormal), normalize(vViewPosition))), 2.05);
  float scan = 0.985 + 0.015 * sin(vPosition.y * 7.0 - uTime * 1.2);
  vec3 color = mix(uCore, uRim, edge) * scan;
  float alpha = clamp((0.22 + edge * 0.54) * uOpacity, 0.04, 0.78);
  gl_FragColor = vec4(color, alpha);
}`;

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
renderer.setSize(mount.clientWidth, mount.clientHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
renderer.domElement.setAttribute("aria-hidden", "true");
mount.appendChild(renderer.domElement);
const modelStatus = document.getElementById('body-model-status');

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(36, mount.clientWidth / Math.max(1, mount.clientHeight), 0.1, 80);
camera.position.set(0, 0.72, 4.6);
const target = new THREE.Vector3(0, 0.67, 0);
camera.lookAt(target);

scene.add(new THREE.AmbientLight(0x456c9b, 1.05));
const keyLight = new THREE.PointLight(0x66d8ff, 5.1, 5.5);
keyLight.position.set(-1.8, 1.7, 2.7);
scene.add(keyLight);
const fillLight = new THREE.PointLight(0x4078ff, 3.2, 5.0);
fillLight.position.set(1.8, 0.1, -1.4);
scene.add(fillLight);
const heartLight = new THREE.PointLight(0xf25f72, 1.8, 1.8);
heartLight.position.set(-0.07, 1.17, 0.36);
scene.add(heartLight);

const person = new THREE.Group();
scene.add(person);
const generatedBody = new THREE.Group();
person.add(generatedBody);
const shellMaterial = new THREE.ShaderMaterial({
  vertexShader,
  fragmentShader,
  uniforms: {
    uRim: { value: new THREE.Color(0x8aeaff) },
    uCore: { value: new THREE.Color(0x34789a) },
    uTime: { value: 0 },
    uOpacity: { value: 1 },
  },
  transparent: true,
  depthWrite: false,
  side: THREE.DoubleSide,
  blending: THREE.NormalBlending,
});
const shellWire = new THREE.MeshBasicMaterial({ color: 0x75dff4, wireframe: true, transparent: true, opacity: 0.085, depthWrite: false });

function loft(profile, radialSegments = 32, wire = true) {
  const positions = [];
  const indices = [];
  const smooth = [];
  const catmull = (p0, p1, p2, p3, t) => 0.5 * ((2 * p1) + (-p0 + p2) * t + (2*p0 - 5*p1 + 4*p2 - p3) * t*t + (-p0 + 3*p1 - 3*p2 + p3) * t*t*t);
  for (let i=0; i<profile.length-1; i++) {
    const a=profile[Math.max(0,i-1)], b=profile[i], c=profile[i+1], d=profile[Math.min(profile.length-1,i+2)];
    for (let step=0; step<4; step++) {
      const t=step/4;
      smooth.push(b.map((value,k)=>catmull(a[k]??0,value,c[k]??0,d[k]??0,t)));
    }
  }
  smooth.push(profile[profile.length-1]);
  smooth.forEach(([y, rawRx, rawRz, zOffset = 0]) => {
    const rx=Math.max(.004,rawRx), rz=Math.max(.004,rawRz);
    for (let j = 0; j <= radialSegments; j++) {
      const a = j / radialSegments * Math.PI * 2;
      positions.push(Math.cos(a) * rx, y, Math.sin(a) * rz + zOffset);
    }
  });
  const stride = radialSegments + 1;
  for (let i = 0; i < smooth.length - 1; i++) {
    for (let j = 0; j < radialSegments; j++) {
      const a = i * stride + j, b = (i + 1) * stride + j, c = b + 1, d = a + 1;
      indices.push(a, b, d, b, c, d);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const group = new THREE.Group();
  group.add(new THREE.Mesh(geometry, shellMaterial));
  if (wire) group.add(new THREE.Mesh(geometry, shellWire));
  return group;
}

const bodyProfile = [
  [1.99,.02,.02,0],[1.95,.11,.13,0],[1.88,.155,.175,.005],[1.8,.16,.18,.01],
  [1.72,.145,.165,.01],[1.64,.12,.14,.005],[1.58,.095,.105,0],[1.5,.105,.105,-.005],
  [1.43,.15,.12,-.005],[1.37,.37,.17,0],[1.28,.38,.205,.01],[1.16,.345,.21,.02],
  [1.04,.31,.19,.01],[.92,.275,.17,.005],[.8,.255,.16,0],[.68,.295,.18,0],[.56,.31,.185,0],[.46,.26,.15,0]
];
generatedBody.add(loft(bodyProfile, 40, true));

function addArm(side) {
  const arm = new THREE.Group();
  arm.position.set(side * .405, 1.35, 0);
  arm.rotation.z = side * .12;
  arm.add(loft([[.02,.105,.105],[-.1,.088,.088],[-.24,.078,.078],[-.36,.07,.07],[-.48,.073,.068],[-.64,.055,.048],[-.75,.045,.037]], 24, true));
  const palm=loft([[-.73,.045,.03],[-.79,.062,.027],[-.86,.055,.023],[-.88,.048,.02]],20,true);
  arm.add(palm);
  for(let finger=0;finger<4;finger++){
    const x=(finger-1.5)*.023;
    const length=.115-Math.abs(finger-1.5)*.012;
    const digit=loft([[-.85,.012,.012],[-.88,.011,.01],[-.88-length*.72,.009,.008],[-.88-length,.006,.006]],12,false);
    digit.position.x=x;
    arm.add(digit);
  }
  const thumb=loft([[-.79,.014,.013],[-.81,.013,.011],[-.86,.01,.009],[-.9,.007,.007]],12,false);
  thumb.position.x=side*.06;
  thumb.rotation.z=-side*.55;
  arm.add(thumb);
  generatedBody.add(arm);
}
addArm(-1);
addArm(1);

const legProfile = [[.54,.142,.14,0],[.38,.13,.13,0],[.2,.106,.105,0],[.04,.09,.09,0],[-.12,.102,.103,-.005],[-.3,.08,.08,0],[-.48,.058,.062,0],[-.56,.068,.125,.035],[-.59,.06,.13,.04]];
for (const side of [-1, 1]) {
  const leg = loft(legProfile, 28, true);
  leg.position.x = side * .165;
  generatedBody.add(leg);
}

const anatomyMeshes = { skin: [], muscles: [], skeleton: [], heart: [], lungs: [] };
let skinReady = false;
let anatomyReady = false;
let organsReady = false;
function fitToBody(root, height = 2.55, floor = -.6) {
  root.updateMatrixWorld(true);
  const sourceBounds = new THREE.Box3().setFromObject(root);
  const sourceHeight = sourceBounds.getSize(new THREE.Vector3()).y;
  if (!Number.isFinite(sourceHeight) || sourceHeight <= 0) throw new Error('The anatomy model has invalid bounds.');
  const factor = height / sourceHeight;
  const center = sourceBounds.getCenter(new THREE.Vector3());
  const offset = new THREE.Vector3(-center.x * factor, floor - sourceBounds.min.y * factor, -center.z * factor);
  root.scale.multiplyScalar(factor);
  root.position.add(offset);
  root.updateMatrixWorld(true);
  return { factor, offset };
}
function fitRelatedPart(root, registration) {
  root.scale.multiplyScalar(registration.factor);
  root.position.add(registration.offset);
  root.updateMatrixWorld(true);
}
function syncAnatomyLayers(layer = stage.dataset.layer || 'Full body') {
  shellMaterial.uniforms.uOpacity.value = layer === 'Full body' ? 1 : layer === 'Heart' ? .34 : layer === 'Lungs' ? .18 : .12;
  generatedBody.visible = !skinReady;
  anatomyMeshes.skin.forEach(mesh => { mesh.visible = skinReady; });
  anatomyMeshes.muscles.forEach(mesh => { mesh.visible = false; });
  anatomyMeshes.skeleton.forEach(mesh => { mesh.visible = anatomyReady && layer === 'Skeleton'; });
  anatomyMeshes.heart.forEach(mesh => { mesh.visible = organsReady && (layer === 'Full body' || layer === 'Heart'); });
  anatomyMeshes.lungs.forEach(mesh => { mesh.visible = organsReady && (layer === 'Full body' || layer === 'Lungs'); });
  heart.visible = !organsReady && (layer === 'Full body' || layer === 'Heart');
  heartHalo.visible = heart.visible;
  lungs.visible = !organsReady && (layer === 'Full body' || layer === 'Lungs');
  skeleton.visible = !anatomyReady && layer === 'Skeleton';
}

const dracoLoader = new DRACOLoader().setDecoderPath(new URL('./vendor/three/examples/jsm/libs/draco/gltf/', import.meta.url).href);
const skinLoader = new GLTFLoader().setDRACOLoader(dracoLoader);
skinLoader.load('./models/anatomy-skin.glb', (gltf) => {
  try {
    const skin = gltf.scene;
    const registration = fitToBody(skin);
    skin.traverse((object) => {
      if (!object.isMesh) return;
      const surface = new THREE.BufferGeometry();
      surface.setAttribute('position', object.geometry.getAttribute('position'));
      if (object.geometry.index) surface.setIndex(object.geometry.index);
      object.geometry = mergeVertices(surface, 1e-4);
      // Flatten the anterior pelvic projection in the source skin mesh into a
      // neutral contour while preserving the surrounding skin.
      const skinPositions = object.geometry.getAttribute('position');
      for (let i = 0; i < skinPositions.count; i++) {
        const x = skinPositions.getX(i);
        const y = skinPositions.getY(i);
        const z = skinPositions.getZ(i);
        const nx = Math.abs(x) / .28;
        const ny = Math.abs(y + 1.4) / 1.1;
        if (nx >= 1 || ny >= 1 || z <= .4) continue;
        const centerWeight = (1 - nx * nx) * (1 - ny * ny);
        const neutralSurface = .4 + .1 * centerWeight;
        if (z > neutralSurface) skinPositions.setZ(i, neutralSurface);
      }
      skinPositions.needsUpdate = true;
      object.geometry.computeVertexNormals();
      object.material = shellMaterial;
      anatomyMeshes.skin.push(object);
    });
    person.add(skin);
    skinReady = true;
    syncAnatomyLayers();
    if (modelStatus) modelStatus.hidden = true;
    const organLoader = new GLTFLoader().setDRACOLoader(dracoLoader);
    organLoader.load('./models/anatomy-organs.glb', (organGltf) => {
      try {
        const organs = organGltf.scene;
        fitRelatedPart(organs, registration);
        organs.traverse((object) => {
          if (!object.isMesh) return;
          const structure = object.name.split('__')[0].toLowerCase();
          if (structure === 'heart') {
            object.geometry.computeBoundingBox();
            const center = object.geometry.boundingBox.getCenter(new THREE.Vector3());
            object.geometry.translate(-center.x, -center.y, -center.z);
            object.geometry.scale(.96, .98, .96);
            object.geometry.translate(center.x, center.y, center.z);
            object.material = new THREE.MeshStandardMaterial({ color: 0xe75a69, emissive: 0x7d1c32, emissiveIntensity: .55, roughness: .34, metalness: .02, transparent: true, opacity: .92, depthWrite: false, side: THREE.DoubleSide });
            anatomyMeshes.heart.push(object);
          } else if (structure === 'lungs') {
            object.material = new THREE.MeshStandardMaterial({ color: 0x7777cb, emissive: 0x302c79, emissiveIntensity: .24, roughness: .42, transparent: true, opacity: .34, depthWrite: false, side: THREE.DoubleSide });
            anatomyMeshes.lungs.push(object);
          } else {
            object.visible = false;
          }
        });
        person.add(organs);
        organsReady = anatomyMeshes.heart.length > 0 && anatomyMeshes.lungs.length > 0;
        syncAnatomyLayers();
      } catch (error) {
        console.warn('Detailed heart and lung meshes could not be prepared; using the local organ references.', error);
      } finally {
        dracoLoader.dispose();
      }
    }, undefined, (error) => {
      console.warn('Detailed heart and lung meshes could not be loaded; using the local organ references.', error);
      dracoLoader.dispose();
    });
  } catch (error) {
    console.warn('The detailed skin mesh could not be prepared; using the local reference mesh.', error);
  }
}, undefined, (error) => {
  console.warn('The detailed skin mesh could not be loaded; using the local reference mesh.', error);
  if (modelStatus) {
    modelStatus.hidden = false;
    modelStatus.textContent = 'Showing illustrative fallback anatomy.';
  }
  dracoLoader.dispose();
});

const anatomyLoader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
anatomyLoader.load('./models/ecorche.meshopt.glb', (gltf) => {
  try {
    const anatomy = gltf.scene;
    fitToBody(anatomy);
    anatomy.traverse((object) => {
      if (!object.isMesh) return;
      const layer = object.userData.layer;
      if (layer !== 'skeleton' && layer !== 'superficial muscles' && layer !== 'deep muscles') return;
      object.material = new THREE.MeshStandardMaterial({
        color: layer === 'skeleton' ? 0x95d7ea : 0x4ba8e9,
        emissive: layer === 'skeleton' ? 0x164f69 : 0x063e72,
        emissiveIntensity: .8,
        roughness: .38,
        metalness: .08,
        transparent: true,
        opacity: layer === 'skeleton' ? .34 : .12,
        depthWrite: false,
        side: THREE.DoubleSide,
      });
      if (layer === 'skeleton') anatomyMeshes.skeleton.push(object);
      else anatomyMeshes.muscles.push(object);
    });
    person.add(anatomy);
    anatomyReady = true;
    syncAnatomyLayers();
  } catch (error) {
    console.warn('The detailed anatomy layers could not be prepared; using the local reference layer.', error);
  }
}, undefined, (error) => {
  console.warn('The detailed anatomy layers could not be loaded; using the local reference layer.', error);
});

// Heart: sculpted extruded shape with a soft light halo.
const heartShape = new THREE.Shape();
heartShape.moveTo(0, -.09);
heartShape.bezierCurveTo(-.045, -.045, -.14, .025, -.12, .105);
heartShape.bezierCurveTo(-.105, .18, -.025, .18, 0, .125);
heartShape.bezierCurveTo(.035, .19, .12, .17, .13, .1);
heartShape.bezierCurveTo(.145, .025, .055, -.045, 0, -.09);
const heartGeometry = new THREE.ExtrudeGeometry(heartShape, { depth: .075, bevelEnabled: true, bevelSegments: 3, steps: 1, bevelSize: .012, bevelThickness: .012 });
const heart = new THREE.Mesh(heartGeometry, new THREE.MeshStandardMaterial({ color: 0xf09098, emissive: 0xe78383, emissiveIntensity: 1.8, roughness: .3, metalness: .04 }));
heart.position.set(-.055, 1.13, .25);
person.add(heart);
const heartHalo = new THREE.Mesh(new THREE.SphereGeometry(.23, 24, 20), new THREE.MeshBasicMaterial({ color: 0xe78383, transparent: true, opacity: .12, depthWrite: false }));
heartHalo.position.set(-.055, 1.21, .18);
person.add(heartHalo);

const lungs = new THREE.Group();
const lungMaterial = new THREE.MeshStandardMaterial({ color: 0xa99bea, emissive: 0x6657a8, emissiveIntensity: .36, transparent: true, opacity: .48, roughness: .42, side: THREE.DoubleSide, depthWrite: false });
for (const side of [-1, 1]) {
  const lung = new THREE.Mesh(new THREE.SphereGeometry(1, 28, 20), lungMaterial);
  lung.scale.set(.115, .26, .075);
  lung.position.set(side * .14, 1.07, .155);
  lungs.add(lung);
}
person.add(lungs);

const skeleton = new THREE.Group();
const boneMaterial = new THREE.LineBasicMaterial({ color: 0xd9edf1, transparent: true, opacity: .64 });
const ribLines = [];
for (let r=0; r<7; r++) {
  const y=1.31-r*.055, rx=.3-r*.018, rz=.174-r*.009;
  const pts=[];
  for (let s=0; s<=32; s++) {
    const a=s/32*Math.PI*1.78-Math.PI*.39;
    pts.push(new THREE.Vector3(Math.cos(a)*rx, y+Math.sin(a*2)*.012, Math.sin(a)*rz+.02));
  }
  ribLines.push(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),boneMaterial));
}
ribLines.forEach(line=>skeleton.add(line));
skeleton.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,1.4,.19),new THREE.Vector3(0,.65,.19),new THREE.Vector3(0,.5,.16)]),boneMaterial));
for (const side of [-1,1]) {
  skeleton.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(side*.12,1.38,.08),new THREE.Vector3(side*.34,1.33,.06),new THREE.Vector3(side*.48,.99,.06),new THREE.Vector3(side*.52,.58,.05),
  ]),boneMaterial));
  skeleton.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(side*.15,.55,.08),new THREE.Vector3(side*.16,.04,.08),new THREE.Vector3(side*.18,-.42,.08),new THREE.Vector3(side*.18,-.56,.1),
  ]),boneMaterial));
}
person.add(skeleton);

// A translucent 3D ellipsoid with a radial falloff reads as an internal glow,
// without a hard outline or a flat circle drawn over the skin.
const focusGlowMaterial = new THREE.ShaderMaterial({
  uniforms: { uColor: { value: new THREE.Color(0xff5968) }, uOpacity: { value: 0 }, uTime: { value: 0 } },
  vertexShader: `varying vec3 vLocal; void main(){ vLocal=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
  fragmentShader: `uniform vec3 uColor; uniform float uOpacity; uniform float uTime; varying vec3 vLocal; void main(){ float r=length(vLocal.xy); float haze=1.0-smoothstep(.16,1.0,r); float core=1.0-smoothstep(0.0,.52,r); float pulse=.96+.04*sin(uTime*2.2); float alpha=(haze*.22+core*.32)*uOpacity*pulse; if(alpha<.008) discard; gl_FragColor=vec4(uColor,alpha); }`,
  transparent: true, depthTest: false, depthWrite: false, blending: THREE.NormalBlending, side: THREE.DoubleSide,
});
const focusGlow = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 24), focusGlowMaterial);
focusGlow.visible = false;
focusGlow.renderOrder = 100;
focusGlow.frustumCulled = false;
person.add(focusGlow);

const bodyRegions = {
  head: { label: 'Head', point: new THREE.Vector3(0, 1.84, .06), size: [.15,.19,.13], distance: .95 },
  neck: { label: 'Neck', point: new THREE.Vector3(0, 1.55, .1), size: [.09,.11,.08], distance: .75 },
  'left-shoulder': { label: 'Left shoulder', point: new THREE.Vector3(.22, 1.47, .08), size: [.08,.075,.06], distance: 1.2 },
  'right-shoulder': { label: 'Right shoulder', point: new THREE.Vector3(-.22, 1.47, .08), size: [.08,.075,.06], distance: 1.2 },
  'left-shoulder-joint': { label: 'Left shoulder joint', point: new THREE.Vector3(.27, 1.4, .08), size: [.065,.065,.05], distance: .96, layer: 'Skeleton' },
  'right-shoulder-joint': { label: 'Right shoulder joint', point: new THREE.Vector3(-.27, 1.4, .08), size: [.065,.065,.05], distance: .96, layer: 'Skeleton' },
  'left-elbow': { label: 'Left elbow joint', point: new THREE.Vector3(.49, .99, .08), size: [.09,.09,.09], distance: .76, layer: 'Skeleton' },
  'right-elbow': { label: 'Right elbow joint', point: new THREE.Vector3(-.49, .99, .08), size: [.09,.09,.09], distance: .76, layer: 'Skeleton' },
  'left-forearm': { label: 'Left forearm', point: new THREE.Vector3(.49, .79, .08), size: [.1,.16,.08], distance: .83 },
  'right-forearm': { label: 'Right forearm', point: new THREE.Vector3(-.49, .79, .08), size: [.1,.16,.08], distance: .83 },
  'left-hand': { label: 'Left hand', point: new THREE.Vector3(.48, .59, .07), size: [.08,.09,.07], distance: .62 },
  'right-hand': { label: 'Right hand', point: new THREE.Vector3(-.48, .59, .07), size: [.08,.09,.07], distance: .62 },
  'left-finger': { label: 'Left index finger', point: new THREE.Vector3(.515, .47, .07), size: [.018,.032,.018], distance: .42 },
  'right-finger': { label: 'Right index finger', point: new THREE.Vector3(-.515, .47, .07), size: [.018,.032,.018], distance: .42 },
  chest: { label: 'Chest', point: new THREE.Vector3(0, 1.19, .18), size: [.18,.17,.1], distance: 1.12 },
  abdomen: { label: 'Abdomen', point: new THREE.Vector3(0, .84, .17), size: [.16,.18,.1], distance: 1.02 },
  'left-hip': { label: 'Left hip', point: new THREE.Vector3(.19, .56, .14), size: [.12,.12,.09], distance: .96 },
  'right-hip': { label: 'Right hip', point: new THREE.Vector3(-.19, .56, .14), size: [.12,.12,.09], distance: .96 },
  'left-thigh': { label: 'Left thigh', point: new THREE.Vector3(.17, .29, .1), size: [.1,.18,.08], distance: .95 },
  'right-thigh': { label: 'Right thigh', point: new THREE.Vector3(-.17, .29, .1), size: [.1,.18,.08], distance: .95 },
  'left-knee': { label: 'Left knee joint', point: new THREE.Vector3(.17, -.02, .09), size: [.09,.09,.08], distance: .7, layer: 'Skeleton' },
  'right-knee': { label: 'Right knee joint', point: new THREE.Vector3(-.17, -.02, .09), size: [.09,.09,.08], distance: .7, layer: 'Skeleton' },
  'left-lower-leg': { label: 'Left lower leg', point: new THREE.Vector3(.18, -.27, .09), size: [.075,.17,.07], distance: .85 },
  'right-lower-leg': { label: 'Right lower leg', point: new THREE.Vector3(-.18, -.27, .09), size: [.075,.17,.07], distance: .85 },
  'left-ankle': { label: 'Left ankle joint', point: new THREE.Vector3(.18, -.46, .09), size: [.075,.075,.07], distance: .63, layer: 'Skeleton' },
  'right-ankle': { label: 'Right ankle joint', point: new THREE.Vector3(-.18, -.46, .09), size: [.075,.075,.07], distance: .63, layer: 'Skeleton' },
  'left-foot': { label: 'Left foot', point: new THREE.Vector3(.18, -.55, .14), size: [.09,.06,.11], distance: .6 },
  'right-foot': { label: 'Right foot', point: new THREE.Vector3(-.18, -.55, .14), size: [.09,.06,.11], distance: .6 },
};

// Projection platform and restrained scanning rings.
const platform = new THREE.Group();
scene.add(platform);
function ring(y, radius, tubeRadius, color, opacity) {
  const mesh = new THREE.Mesh(new THREE.TorusGeometry(radius, tubeRadius, 8, 112), new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
  mesh.rotation.x = Math.PI/2;
  mesh.position.y = y;
  platform.add(mesh);
  return mesh;
}
ring(-.62,.54,.014,0x65d4e6,.82);
ring(-.64,.68,.009,0x8aa9e8,.5);
ring(-.58,.38,.006,0x65d4e6,.28);
ring(1.2,.53,.006,0x65d4e6,.2);
ring(.62,.55,.005,0x8aa9e8,.16);
ring(.05,.5,.005,0x65d4e6,.14);
const platformDisc = new THREE.Mesh(new THREE.CylinderGeometry(.38,.43,.018,64), new THREE.MeshBasicMaterial({ color: 0x183a53, transparent: true, opacity: .58, wireframe: true }));
platformDisc.position.y=-.64;
platform.add(platformDisc);

const stars = new THREE.Group();
const starPositions=[];
for(let i=0;i<90;i++) starPositions.push((Math.random()-.5)*3.6,(Math.random()*2.7)-.5,-.8-Math.random()*1.8);
const starGeometry=new THREE.BufferGeometry();
starGeometry.setAttribute('position',new THREE.Float32BufferAttribute(starPositions,3));
stars.add(new THREE.Points(starGeometry,new THREE.PointsMaterial({color:0x9bdff0,size:.012,transparent:true,opacity:.38,sizeAttenuation:true})));
scene.add(stars);

let autoRotate = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let dragging = false, lastX = 0, lastY = 0, pointerStartX = 0, pointerStartY = 0;
let desiredDistance = 4.6;
let focusLocalPoint = new THREE.Vector3(0, .67, 0);
let focusTarget = new THREE.Vector3(0, .67, 0);
let focusGlowOpacity = 0;
const bodyAreaSelect = document.getElementById('body-area-select');
const focusStatus = document.getElementById('body-focus-status');
const canvas=renderer.domElement;
canvas.style.cursor='grab';
canvas.addEventListener('pointerdown',e=>{dragging=true;lastX=e.clientX;lastY=e.clientY;pointerStartX=e.clientX;pointerStartY=e.clientY;canvas.setPointerCapture(e.pointerId);canvas.style.cursor='grabbing';});
canvas.addEventListener('pointermove',e=>{
  if(!dragging)return;
  person.rotation.y += (e.clientX-lastX)*.008;
  person.rotation.x = THREE.MathUtils.clamp(person.rotation.x+(e.clientY-lastY)*.004,-.22,.22);
  lastX=e.clientX;lastY=e.clientY;
});
function setLayer(layer){
  stage.dataset.layer=layer;
  syncAnatomyLayers(layer);
  document.querySelectorAll('.body-layer').forEach(button=>button.classList.toggle('active',button.dataset.layer===layer));
}
function focusRegion(regionId, options={}){
  const region=bodyRegions[regionId];
  if(!region)return false;
  const layer=options.layer || region.layer || 'Full body';
  const severity=options.severity || 'red';
  const colors={red:0xff5968,amber:0xffbd68,green:0x4ce0ad};
  person.rotation.set(0,0,0);
  setRotate(false);
  setLayer(layer);
  focusLocalPoint.copy(options.point || region.point);
  person.updateMatrixWorld(true);
  focusTarget.copy(person.localToWorld(focusLocalPoint.clone()));
  desiredDistance=region.distance;
  focusGlow.position.copy(focusLocalPoint);
  focusGlow.scale.set(...region.size);
  focusGlowMaterial.uniforms.uColor.value.setHex(colors[severity] || colors.red);
  focusGlowOpacity=THREE.MathUtils.clamp(Number(options.intensity ?? 1),0,1);
  focusGlow.visible=focusGlowOpacity>.01;
  if(bodyAreaSelect)bodyAreaSelect.value=regionId;
  if(focusStatus)focusStatus.textContent=`Focused on ${region.label}${layer==='Skeleton'?' · skeleton view':''}.`;
  return true;
}
function clearFocus(){
  focusGlowOpacity=0;
  focusGlow.visible=false;
  focusLocalPoint.set(0,.67,0);
  focusTarget.set(0,.67,0);
  desiredDistance=4.6;
  if(focusStatus)focusStatus.textContent='Choose an area or select a point on the model.';
}
window.LunarBodyGuide={
  focusRegion,
  clearFocus,
  regions:Object.fromEntries(Object.entries(bodyRegions).map(([key,value])=>[key,{label:value.label,layer:value.layer||'Full body'}])),
};
window.addEventListener('lunar:focus-body',event=>{
  const detail=event.detail||{};
  focusRegion(detail.region,{layer:detail.layer,severity:detail.severity});
});
const raycaster=new THREE.Raycaster();
const pointer=new THREE.Vector2();
function regionFromPoint(localPoint){
  let closest='chest',closestScore=Infinity;
  for(const [id,region] of Object.entries(bodyRegions)){
    const dx=(localPoint.x-region.point.x)*1.15;
    const dy=(localPoint.y-region.point.y)*.85;
    const dz=(localPoint.z-region.point.z)*.5;
    const score=dx*dx+dy*dy+dz*dz;
    if(score<closestScore){closest=id;closestScore=score;}
  }
  return closest;
}
function pickBodyPoint(event){
  const rect=canvas.getBoundingClientRect();
  pointer.set(((event.clientX-rect.left)/rect.width)*2-1,-((event.clientY-rect.top)/rect.height)*2+1);
  raycaster.setFromCamera(pointer,camera);
  const surfaces=skinReady?anatomyMeshes.skin:generatedBody.children;
  const intersections=raycaster.intersectObjects(surfaces,true);
  if(!intersections.length)return;
  const localPoint=person.worldToLocal(intersections[0].point.clone());
  focusRegion(regionFromPoint(localPoint),{point:localPoint});
}
const stopDrag=e=>{
  const wasClick=Math.hypot(e.clientX-pointerStartX,e.clientY-pointerStartY)<7;
  dragging=false;canvas.style.cursor='grab';
  if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);
  if(wasClick)pickBodyPoint(e);
};
canvas.addEventListener('pointerup',stopDrag);canvas.addEventListener('pointercancel',stopDrag);
function zoom(amount){desiredDistance=THREE.MathUtils.clamp(desiredDistance+amount,.34,6.2);}
canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY*.002);},{passive:false});
mount.addEventListener('keydown',e=>{
  const step=.12;
  if(e.key==='ArrowLeft'){person.rotation.y-=step;e.preventDefault();}
  else if(e.key==='ArrowRight'){person.rotation.y+=step;e.preventDefault();}
  else if(e.key==='ArrowUp'){zoom(-.18);e.preventDefault();}
  else if(e.key==='ArrowDown'){zoom(.18);e.preventDefault();}
});

const rotateButton=document.getElementById('body-rotate');
function setRotate(next){autoRotate=next;if(rotateButton){rotateButton.setAttribute('aria-pressed',String(next));const text=rotateButton.querySelector('span');if(text)text.textContent=next?'Pause':'Rotate';}}
if(rotateButton){setRotate(autoRotate);rotateButton.addEventListener('click',()=>setRotate(!autoRotate));}
document.querySelectorAll('.body-layer').forEach(button=>button.addEventListener('click',()=>setLayer(button.dataset.layer)));
document.getElementById('body-focus-button')?.addEventListener('click',()=>focusRegion(bodyAreaSelect?.value));
document.getElementById('body-zoom-in')?.addEventListener('click',()=>zoom(-.3));
document.getElementById('body-zoom-out')?.addEventListener('click',()=>zoom(.3));
document.getElementById('body-reset')?.addEventListener('click',()=>{
  person.rotation.set(0,0,0);target.set(0,.67,0);camera.position.set(0,.72,4.6);camera.lookAt(target);
  clearFocus();setRotate(!window.matchMedia('(prefers-reduced-motion: reduce)').matches);setLayer('Full body');
});
document.getElementById('body-fullscreen')?.addEventListener('click',()=>{
  const card=document.querySelector('.body-explorer-card');
  if(!document.fullscreenElement) card?.requestFullscreen?.(); else document.exitFullscreen?.();
});

let frameId=0, previous=performance.now();
const desiredCameraPosition=new THREE.Vector3();
function animate(now){
  frameId=requestAnimationFrame(animate);
  const dt=Math.min((now-previous)/1000,.05);previous=now;
  shellMaterial.uniforms.uTime.value=now*.001;
  focusGlowMaterial.uniforms.uTime.value=now*.001;
  focusGlowMaterial.uniforms.uOpacity.value=focusGlowOpacity;
  if(autoRotate&&!dragging)person.rotation.y+=dt*.12;
  person.updateMatrixWorld(true);
  focusTarget.copy(person.localToWorld(focusLocalPoint.clone()));
  target.lerp(focusTarget,.12);
  desiredCameraPosition.set(focusTarget.x,focusTarget.y+.05,focusTarget.z+desiredDistance);
  camera.position.lerp(desiredCameraPosition,.12);
  camera.lookAt(target);
  renderer.render(scene,camera);
}
const resizeObserver=new ResizeObserver(()=>{
  const width=mount.clientWidth,height=mount.clientHeight;
  if(!width||!height)return;
  camera.aspect=width/height;camera.updateProjectionMatrix();renderer.setSize(width,height);
});
resizeObserver.observe(mount);
function visibilityChange(){if(document.hidden){cancelAnimationFrame(frameId);}else{previous=performance.now();frameId=requestAnimationFrame(animate);}}
document.addEventListener('visibilitychange',visibilityChange);
frameId=requestAnimationFrame(animate);

window.addEventListener('pagehide',()=>{
  cancelAnimationFrame(frameId);resizeObserver.disconnect();renderer.dispose();
});


