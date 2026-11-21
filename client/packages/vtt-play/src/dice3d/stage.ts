// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The dice tray's 3D stage: three.js draws the dice (from faces.ts' geometry, each face carrying its
 * label) and replays a recorded throw, then stops. It draws only while a replay runs: once the dice
 * settle the canvas holds its last frame and no frame is requested (zero idle frames). Colours come
 * from the page's theme tokens, so the dice follow light and dark.
 */
import {
  AmbientLight,
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  DirectionalLight,
  Group,
  Mesh,
  MeshStandardMaterial,
  PerspectiveCamera,
  Scene,
  SRGBColorSpace,
  WebGLRenderer,
} from 'three';
import { geometryOf, type DieFaces, type Vec3 } from './faces';
import { STEP, type Throw } from './simulate';

/** No tumble lasts longer than this on screen. */
export const REPLAY_SECONDS = 2.5;

export interface Theme {
  face: string;
  ink: string;
}

/** The die's surface and number colours from the theme tokens (any CSS colour a canvas accepts). */
export function themeOf(element: Element): Theme {
  const style = getComputedStyle(element);
  const token = (name: string, fallback: string): string => {
    const value = style.getPropertyValue(name).trim();
    if (!value) return fallback;
    return /^[\d.]+(%|\s)/.test(value) ? `oklch(${value})` : value;
  };
  return { face: token('--primary', '#7a34f2'), ink: token('--primary-foreground', '#ffffff') };
}

function labelTexture(label: string, theme: Theme): CanvasTexture {
  const size = 128;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const context = canvas.getContext('2d')!;
  context.fillStyle = theme.face;
  context.fillRect(0, 0, size, size);
  context.fillStyle = theme.ink;
  context.font = `600 ${label.length > 1 ? 44 : 56}px system-ui, sans-serif`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(label, size / 2, size / 2);
  if (label === '6' || label === '9') context.fillRect(size / 2 - 14, size / 2 + 30, 28, 5); // tell 6 from 9
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  return texture;
}

/** One face's corners in its own plane, scaled into [0.15, 0.85] so the label sits in the middle. */
function faceUVs(corners: Vec3[], normal: Vec3): [number, number][] {
  const ox = corners.reduce((sum, corner) => sum + corner[0], 0) / corners.length;
  const oy = corners.reduce((sum, corner) => sum + corner[1], 0) / corners.length;
  const oz = corners.reduce((sum, corner) => sum + corner[2], 0) / corners.length;
  const first = corners[0]!;
  let u: Vec3 = [first[0] - ox, first[1] - oy, first[2] - oz];
  const ul = Math.hypot(...u);
  u = [u[0] / ul, u[1] / ul, u[2] / ul];
  const v: Vec3 = [
    normal[1] * u[2] - normal[2] * u[1],
    normal[2] * u[0] - normal[0] * u[2],
    normal[0] * u[1] - normal[1] * u[0],
  ];
  const flat = corners.map(([x, y, z]): [number, number] => {
    const d: Vec3 = [x - ox, y - oy, z - oz];
    return [d[0] * u[0] + d[1] * u[1] + d[2] * u[2], d[0] * v[0] + d[1] * v[1] + d[2] * v[2]];
  });
  const reach = Math.max(...flat.map(([a, b]) => Math.max(Math.abs(a), Math.abs(b))));
  return flat.map(([a, b]) => [0.5 + (0.35 * a) / reach, 0.5 + (0.35 * b) / reach]);
}

function dieMesh(faces: DieFaces, theme: Theme, textures: Map<string, CanvasTexture>): Mesh {
  const { vertices, faces: polygons } = geometryOf(faces.kind);
  const positions: number[] = [];
  const uvs: number[] = [];
  const geometry = new BufferGeometry();
  let start = 0;
  polygons.forEach((polygon, index) => {
    const corners = polygon.map((corner) => vertices[corner]!);
    const flat = faceUVs(corners, faces.normals[index]!);
    for (let i = 1; i < corners.length - 1; i += 1) {
      for (const at of [0, i, i + 1]) {
        positions.push(...corners[at]!);
        uvs.push(...flat[at]!);
      }
    }
    const count = (corners.length - 2) * 3;
    geometry.addGroup(start, count, index);
    start += count;
  });
  geometry.setAttribute('position', new BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute('uv', new BufferAttribute(new Float32Array(uvs), 2));
  geometry.computeVertexNormals();
  const materials = faces.labels.map((label) => {
    if (!textures.has(label)) textures.set(label, labelTexture(label, theme));
    return new MeshStandardMaterial({ map: textures.get(label)!, roughness: 0.45, metalness: 0.05, flatShading: true });
  });
  return new Mesh(geometry, materials);
}

export interface Stage {
  /** Replays the throw with each die showing its faces; resolves when the dice rest. */
  play(thrown: Throw, faces: DieFaces[], animate: boolean): Promise<void>;
  dispose(): void;
}

export function createStage(canvas: HTMLCanvasElement): Stage {
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new Scene();
  const camera = new PerspectiveCamera(35, 1, 0.1, 100);
  camera.position.set(0, 16, 6);
  camera.lookAt(0, 0, 0);
  scene.add(new AmbientLight(0xffffff, 1.2));
  const sun = new DirectionalLight(0xffffff, 2);
  sun.position.set(4, 10, 6);
  scene.add(sun);
  const dice = new Group();
  scene.add(dice);
  const textures = new Map<string, CanvasTexture>();
  let frame = 0;

  const fit = (): void => {
    const { clientWidth: width, clientHeight: height } = canvas;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
  };

  const pose = (meshes: Mesh[], values: number[]): void => {
    meshes.forEach((mesh, die) => {
      const at = die * 7;
      mesh.position.set(values[at]!, values[at + 1]!, values[at + 2]!);
      mesh.quaternion.set(values[at + 3]!, values[at + 4]!, values[at + 5]!, values[at + 6]!);
    });
  };

  return {
    play(thrown, faces, animate) {
      cancelAnimationFrame(frame);
      dice.clear();
      const theme = themeOf(canvas);
      for (const texture of textures.values()) texture.dispose();
      textures.clear();
      const meshes = faces.map((one) => dieMesh(one, theme, textures));
      meshes.forEach((mesh) => dice.add(mesh));
      fit();
      const last = thrown.frames.length - 1;
      if (!animate || last < 0) {
        if (last >= 0) pose(meshes, thrown.frames[last]!);
        renderer.render(scene, camera);
        return Promise.resolve();
      }
      // A long settle plays faster, so every tumble is over within REPLAY_SECONDS.
      const speed = Math.max(1, (last * STEP) / REPLAY_SECONDS);
      return new Promise((resolve) => {
        const started = performance.now();
        const tick = (now: number): void => {
          const index = Math.min(last, Math.floor(((now - started) / 1000 / STEP) * speed));
          pose(meshes, thrown.frames[index]!);
          renderer.render(scene, camera);
          if (index < last) frame = requestAnimationFrame(tick);
          else resolve();
        };
        frame = requestAnimationFrame(tick);
      });
    },
    dispose() {
      cancelAnimationFrame(frame);
      for (const texture of textures.values()) texture.dispose();
      renderer.dispose();
    },
  };
}
