// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The dice's faces and how a settled die is read and relabelled, with no rendering or physics: the
 * server's roll is the result, and a tumble only has to end showing it. After a headless throw
 * settles, `upFace` finds the face pointing up; `relabel` swaps labels so that face carries the
 * server's value (the physics stays real, only the numbering moves). Plain vectors and quaternions,
 * so it runs in a worker and in tests without three.js.
 */

export type DieKind = 'd6' | 'd10' | 'd10-tens' | 'd20';

export type Vec3 = readonly [number, number, number];
/** x, y, z, w */
export type Quat = readonly [number, number, number, number];

export interface DieGeometry {
  /** Corner points, in the die's own frame (about unit radius). */
  vertices: Vec3[];
  /** Each face's corner indices, counter-clockwise seen from outside. */
  faces: number[][];
}

export interface DieFaces {
  kind: DieKind;
  /** Outward unit normals, one per face, in the die's own frame. */
  normals: Vec3[];
  /** The label each face shows, by face index. */
  labels: string[];
}

const PHI = (1 + Math.sqrt(5)) / 2;

function sub(p: Vec3, q: Vec3): Vec3 {
  return [p[0] - q[0], p[1] - q[1], p[2] - q[2]];
}

function cross(p: Vec3, q: Vec3): Vec3 {
  return [p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0]];
}

function dot(p: Vec3, q: Vec3): number {
  return p[0] * q[0] + p[1] * q[1] + p[2] * q[2];
}

function normalize([x, y, z]: Vec3): Vec3 {
  const length = Math.hypot(x, y, z);
  return [x / length, y / length, z / length];
}

function centroid(points: Vec3[]): Vec3 {
  const sum = points.reduce<Vec3>(
    (total, point) => [total[0] + point[0], total[1] + point[1], total[2] + point[2]],
    [0, 0, 0],
  );
  return [sum[0] / points.length, sum[1] / points.length, sum[2] / points.length];
}

/** A face's outward normal (the solids are convex and centred on the origin). */
function faceNormal(vertices: Vec3[], face: number[]): Vec3 {
  const [a, b, c] = face.map((index) => vertices[index]!) as [Vec3, Vec3, Vec3];
  const normal = normalize(cross(sub(b, a), sub(c, a)));
  return dot(normal, centroid(face.map((index) => vertices[index]!))) < 0 ? [-normal[0], -normal[1], -normal[2]] : normal;
}

/** Faces wound counter-clockwise from outside, as a physics engine's convex shapes need. */
function wound(vertices: Vec3[], faces: number[][]): number[][] {
  return faces.map((face) => {
    const [a, b, c] = face.map((index) => vertices[index]!) as [Vec3, Vec3, Vec3];
    const outward = dot(cross(sub(b, a), sub(c, a)), centroid(face.map((index) => vertices[index]!))) > 0;
    return outward ? face : [...face].reverse();
  });
}

function cube(): DieGeometry {
  const vertices: Vec3[] = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) vertices.push([x * 0.7, y * 0.7, z * 0.7]);
  const at = (x: number, y: number, z: number): number => (x > 0 ? 4 : 0) + (y > 0 ? 2 : 0) + (z > 0 ? 1 : 0);
  const faces = [
    [at(-1, 1, -1), at(-1, 1, 1), at(1, 1, 1), at(1, 1, -1)],
    [at(-1, -1, -1), at(1, -1, -1), at(1, -1, 1), at(-1, -1, 1)],
    [at(1, -1, -1), at(1, 1, -1), at(1, 1, 1), at(1, -1, 1)],
    [at(-1, -1, -1), at(-1, -1, 1), at(-1, 1, 1), at(-1, 1, -1)],
    [at(-1, -1, 1), at(1, -1, 1), at(1, 1, 1), at(-1, 1, 1)],
    [at(-1, -1, -1), at(-1, 1, -1), at(1, 1, -1), at(1, -1, -1)],
  ];
  return { vertices, faces: wound(vertices, faces) };
}

/** The icosahedron: each face's three corners are mutually an edge (2) apart. */
function icosahedron(): DieGeometry {
  const corners: Vec3[] = [];
  for (const a of [-1, 1]) for (const b of [-PHI, PHI]) corners.push([0, a, b], [a, b, 0], [b, 0, a]);
  const near = (p: Vec3, q: Vec3): boolean => Math.abs(Math.hypot(...sub(p, q)) - 2) < 1e-9;
  const faces: number[][] = [];
  for (let i = 0; i < corners.length; i += 1)
    for (let j = i + 1; j < corners.length; j += 1)
      for (let k = j + 1; k < corners.length; k += 1)
        if (near(corners[i]!, corners[j]!) && near(corners[j]!, corners[k]!) && near(corners[i]!, corners[k]!))
          faces.push([i, j, k]);
  const scale = 1 / Math.hypot(1, PHI);
  const vertices = corners.map(([x, y, z]): Vec3 => [x * scale, y * scale, z * scale]);
  return { vertices, faces: wound(vertices, faces) };
}

/**
 * The d10, a pentagonal trapezohedron: two apexes and two rings of five, offset by 36°. The apex
 * height makes each kite planar: h = e·(1 + cos 36°)/(1 − cos 36°) for rings at ±e.
 */
const RING = 0.1;
const APEX = (RING * (1 + Math.cos(Math.PI / 5))) / (1 - Math.cos(Math.PI / 5));
function trapezohedron(): DieGeometry {
  const at = (degrees: number, y: number): Vec3 => [
    Math.cos((degrees * Math.PI) / 180),
    y,
    Math.sin((degrees * Math.PI) / 180),
  ];
  const vertices: Vec3[] = [
    [0, APEX, 0],
    [0, -APEX, 0],
  ];
  for (let k = 0; k < 5; k += 1) vertices.push(at(k * 72, RING));
  for (let k = 0; k < 5; k += 1) vertices.push(at(k * 72 + 36, -RING));
  const upper = (k: number): number => 2 + (k % 5);
  const lower = (k: number): number => 7 + (k % 5);
  const faces: number[][] = [];
  for (let k = 0; k < 5; k += 1) {
    faces.push([0, upper(k), lower(k), upper(k + 1)]);
    faces.push([1, lower(k), upper(k + 1), lower(k + 1)]);
  }
  return { vertices, faces: wound(vertices, faces) };
}

export function geometryOf(kind: DieKind): DieGeometry {
  if (kind === 'd6') return cube();
  if (kind === 'd20') return icosahedron();
  return trapezohedron();
}

function range(from: number, count: number, step = 1): string[] {
  return Array.from({ length: count }, (_, index) => String(from + index * step));
}

export function facesOf(kind: DieKind): DieFaces {
  const { vertices, faces } = geometryOf(kind);
  const normals = faces.map((face) => faceNormal(vertices, face));
  const labels =
    kind === 'd6'
      ? range(1, 6)
      : kind === 'd20'
        ? range(1, 20)
        : kind === 'd10'
          ? range(0, 10)
          : range(0, 10, 10).map((label) => label.padStart(2, '0'));
  return { kind, normals, labels };
}

/** A vector rotated by a unit quaternion. */
export function rotate([x, y, z]: Vec3, [qx, qy, qz, qw]: Quat): Vec3 {
  const tx = 2 * (qy * z - qz * y);
  const ty = 2 * (qz * x - qx * z);
  const tz = 2 * (qx * y - qy * x);
  return [x + qw * tx + (qy * tz - qz * ty), y + qw * ty + (qz * tx - qx * tz), z + qw * tz + (qx * ty - qy * tx)];
}

/** The face pointing most nearly up (+y) once the die rests with this orientation. */
export function upFace(faces: DieFaces, orientation: Quat): number {
  let best = 0;
  let highest = -Infinity;
  faces.normals.forEach((normal, index) => {
    const up = rotate(normal, orientation)[1];
    if (up > highest) {
      highest = up;
      best = index;
    }
  });
  return best;
}

/** The labels with ``face`` showing ``label``: swapped with the face that showed it. */
export function relabel(faces: DieFaces, face: number, label: string): DieFaces {
  const from = faces.labels.indexOf(label);
  if (from < 0) throw new Error(`a ${faces.kind} has no face ${label}`);
  const labels = [...faces.labels];
  [labels[face], labels[from]] = [labels[from]!, labels[face]!];
  return { ...faces, labels };
}

export interface ShownDie {
  kind: DieKind;
  label: string;
}

/**
 * The dice that show a server result. A d100 is a tens die and a units die (100 shows 00 and 0,
 * as the books read it); other sizes show their own value.
 */
export function diceFor(sides: number, value: number): ShownDie[] {
  if (sides === 100) {
    const units = value % 10;
    const tens = Math.floor((value % 100) / 10) * 10;
    return [
      { kind: 'd10-tens', label: String(tens).padStart(2, '0') },
      { kind: 'd10', label: String(units) },
    ];
  }
  if (sides === 10) return [{ kind: 'd10', label: String(value % 10) }];
  if (sides === 6 || sides === 20) return [{ kind: `d${sides}` as DieKind, label: String(value) }];
  throw new Error(`no 3D die for d${sides}`);
}
