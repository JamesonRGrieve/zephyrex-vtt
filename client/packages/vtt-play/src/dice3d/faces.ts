// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The dice's faces and how a settled die is read and relabelled, with no rendering or physics: the
 * server's roll is the result, and a tumble only has to end showing it. After a headless throw
 * settles, `upFace` finds the face pointing up; `relabel` swaps labels so that face carries the
 * server's value (the physics stays real, only the numbering moves). Plain vectors and quaternions,
 * so it runs in a worker and in tests without three.js.
 */

export type DieKind = 'd4' | 'd6' | 'd8' | 'd10' | 'd10-tens' | 'd12' | 'd20';

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

/**
 * A solid's faces from their outward directions: each face is the corners furthest along its
 * direction, ordered around it (so the solids below are just their corners and face directions).
 */
function facesAlong(vertices: Vec3[], directions: Vec3[]): number[][] {
  return directions.map((direction) => {
    const along = vertices.map((vertex) => dot(vertex, direction));
    const most = Math.max(...along);
    const corners = vertices.flatMap((_, index) => (Math.abs(along[index]! - most) < 1e-6 ? [index] : []));
    const centre = centroid(corners.map((index) => vertices[index]!));
    const normal = normalize(direction);
    const first = normalize(sub(vertices[corners[0]!]!, centre));
    const second = cross(normal, first);
    const angle = (index: number): number => {
      const offset = sub(vertices[index]!, centre);
      return Math.atan2(dot(offset, second), dot(offset, first));
    };
    return [...corners].sort((a, b) => angle(a) - angle(b));
  });
}

function scaled(vertices: Vec3[], radius: number): Vec3[] {
  const reach = Math.max(...vertices.map((vertex) => Math.hypot(...vertex)));
  return vertices.map(([x, y, z]): Vec3 => [(x * radius) / reach, (y * radius) / reach, (z * radius) / reach]);
}

/** The d4: a regular tetrahedron (alternate corners of a cube). */
function tetrahedron(): DieGeometry {
  const vertices = scaled(
    [
      [1, 1, 1],
      [1, -1, -1],
      [-1, 1, -1],
      [-1, -1, 1],
    ],
    1.1,
  );
  const directions = vertices.map(([x, y, z]): Vec3 => [-x, -y, -z]);
  return { vertices, faces: wound(vertices, facesAlong(vertices, directions)) };
}

/** The d8: a regular octahedron, its corners on the axes and a face in each octant. */
function octahedron(): DieGeometry {
  const vertices: Vec3[] = [
    [1, 0, 0],
    [-1, 0, 0],
    [0, 1, 0],
    [0, -1, 0],
    [0, 0, 1],
    [0, 0, -1],
  ];
  const directions: Vec3[] = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) directions.push([x, y, z]);
  return { vertices, faces: wound(vertices, facesAlong(vertices, directions)) };
}

/** The d12: a regular dodecahedron; its faces point at an icosahedron's corners. */
function dodecahedron(): DieGeometry {
  const corners: Vec3[] = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) corners.push([x, y, z]);
  for (const a of [-1, 1])
    for (const b of [-1, 1]) corners.push([0, a / PHI, b * PHI], [a / PHI, b * PHI, 0], [b * PHI, 0, a / PHI]);
  const directions: Vec3[] = [];
  for (const a of [-1, 1]) for (const b of [-PHI, PHI]) directions.push([0, b, a], [b, a, 0], [a, 0, b]);
  const vertices = scaled(corners, 1);
  return { vertices, faces: wound(vertices, facesAlong(vertices, directions)) };
}

export function geometryOf(kind: DieKind): DieGeometry {
  if (kind === 'd4') return tetrahedron();
  if (kind === 'd6') return cube();
  if (kind === 'd8') return octahedron();
  if (kind === 'd12') return dodecahedron();
  if (kind === 'd20') return icosahedron();
  return trapezohedron();
}

/** Whether a die is read by the face it rests on (a d4, which has no face pointing up). */
export function readDown(kind: DieKind): boolean {
  return kind === 'd4';
}

function range(from: number, count: number, step = 1): string[] {
  return Array.from({ length: count }, (_, index) => String(from + index * step));
}

export function facesOf(kind: DieKind): DieFaces {
  const { vertices, faces } = geometryOf(kind);
  const normals = faces.map((face) => faceNormal(vertices, face));
  const labels =
    kind === 'd10'
      ? range(0, 10)
      : kind === 'd10-tens'
        ? range(0, 10, 10).map((label) => label.padStart(2, '0'))
        : range(1, faces.length);
  return { kind, normals, labels };
}

/** A vector rotated by a unit quaternion. */
export function rotate([x, y, z]: Vec3, [qx, qy, qz, qw]: Quat): Vec3 {
  const tx = 2 * (qy * z - qz * y);
  const ty = 2 * (qz * x - qx * z);
  const tz = 2 * (qx * y - qy * x);
  return [x + qw * tx + (qy * tz - qz * ty), y + qw * ty + (qz * tx - qx * tz), z + qw * tz + (qx * ty - qy * tx)];
}

/**
 * The face that reads the die once it rests with this orientation: the one pointing most nearly up
 * (+y), or for a die read down (a d4) the one it rests on.
 */
export function upFace(faces: DieFaces, orientation: Quat): number {
  let best = 0;
  let highest = -Infinity;
  const sign = readDown(faces.kind) ? -1 : 1;
  faces.normals.forEach((normal, index) => {
    const up = sign * rotate(normal, orientation)[1];
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
  // A die read down shows its value on every face, so it reads from wherever it's seen.
  if (readDown(faces.kind)) return { ...faces, labels: faces.labels.map(() => label) };
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
  if ([4, 6, 8, 12, 20].includes(sides)) return [{ kind: `d${sides}` as DieKind, label: String(value) }];
  throw new Error(`no 3D die for d${sides}`);
}
