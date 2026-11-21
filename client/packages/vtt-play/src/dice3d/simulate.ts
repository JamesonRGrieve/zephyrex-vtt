// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * A headless throw: cannon-es tumbles the dice in a walled tray until they rest, and records every
 * frame. Nothing here decides a result; the frames are replayed with the faces relabelled to the
 * server's roll (faces.ts). Seeded, so the same seed throws the same tumble on every seat.
 */
import { Body, Box, ConvexPolyhedron, Plane, Quaternion, Vec3 as CannonVec3, World } from 'cannon-es';
import { facesOf, geometryOf, rotate, upFace, type DieKind, type Quat, type Vec3 } from './faces';

export const STEP = 1 / 60;
/** At most this long, then the frames stop wherever the dice are (10 s of simulated time; the replay
 * compresses it, see stage.ts). Headless, this costs milliseconds. */
export const MAX_FRAMES = 600;
/** A cocked throw (a die resting on an edge or another die) is thrown again with the next seed, at
 * most this many times: still deterministic, so every seat lands the same. */
export const ATTEMPTS = 6;
/** The tray's half-width and half-depth (die radius ≈ 1). */
export const TRAY: readonly [number, number] = [5, 3.2];

export interface Throw {
  kinds: DieKind[];
  /** The seed actually thrown (the asked one, or a later one when a throw came to rest cocked). */
  seed: number;
  /** Per frame, per die: x, y, z, then the quaternion x, y, z, w. */
  frames: number[][];
  /** Each die's resting orientation (the last frame's). */
  rests: Quat[];
  settled: boolean;
}

/** mulberry32: a small seeded generator, the same sequence for the same seed everywhere. */
export function seeded(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function vec([x, y, z]: Vec3): CannonVec3 {
  return new CannonVec3(x, y, z);
}

function shapeOf(kind: DieKind): Box | ConvexPolyhedron {
  if (kind === 'd6') return new Box(new CannonVec3(0.7, 0.7, 0.7));
  const { vertices, faces } = geometryOf(kind);
  return new ConvexPolyhedron({ vertices: vertices.map(vec), faces });
}

function wall(world: World, position: Vec3, axis: Vec3, angle: number): void {
  const body = new Body({ mass: 0, shape: new Plane() });
  body.position.set(...position);
  body.quaternion.setFromAxisAngle(vec(axis), angle);
  world.addBody(body);
}

/** Every die rests flat on a face (its up face within ~18° of vertical). */
function flat(kinds: DieKind[], rests: Quat[]): boolean {
  return kinds.every((kind, index) => {
    const faces = facesOf(kind);
    const rest = rests[index]!;
    return rotate(faces.normals[upFace(faces, rest)]!, rest)[1] > 0.95;
  });
}

export function simulateThrow(kinds: DieKind[], seed: number): Throw {
  let thrown = throwOnce(kinds, seed);
  for (let attempt = 1; attempt < ATTEMPTS && !thrown.settled; attempt += 1) thrown = throwOnce(kinds, seed + attempt);
  return thrown;
}

// Tuned on 58137 over 30 seeds (probe2): all settle inside the tray, median ~2.7 s simulated.
const DAMPING = 0.2;
const ANGULAR_DAMPING = 0.3;

function throwOnce(kinds: DieKind[], seed: number): Throw {
  const random = seeded(seed);
  const world = new World({ gravity: new CannonVec3(0, -30, 0) });
  world.defaultContactMaterial.friction = 0.4;
  world.defaultContactMaterial.restitution = 0.3;
  const [width, depth] = TRAY;
  wall(world, [0, 0, 0], [1, 0, 0], -Math.PI / 2); // floor, facing up
  wall(world, [-width, 0, 0], [0, 1, 0], Math.PI / 2);
  wall(world, [width, 0, 0], [0, 1, 0], -Math.PI / 2);
  wall(world, [0, 0, -depth], [0, 1, 0], 0);
  wall(world, [0, 0, depth], [0, 1, 0], Math.PI);

  const bodies = kinds.map((kind, index) => {
    const body = new Body({ mass: 1, shape: shapeOf(kind), linearDamping: DAMPING, angularDamping: ANGULAR_DAMPING });
    const lane = kinds.length === 1 ? 0 : (index / (kinds.length - 1) - 0.5) * depth;
    body.position.set(-width + 1.2, 2.5 + random() * 1.5, lane + (random() - 0.5));
    const axis = new CannonVec3(random() - 0.5, random() - 0.5, random() - 0.5);
    axis.normalize();
    body.quaternion.setFromAxisAngle(axis, random() * Math.PI * 2);
    body.velocity.set(9 + random() * 6, 2 + random() * 3, (random() - 0.5) * 6);
    body.angularVelocity.set((random() - 0.5) * 30, (random() - 0.5) * 30, (random() - 0.5) * 30);
    world.addBody(body);
    return body;
  });

  const frames: number[][] = [];
  let still = 0;
  for (let frame = 0; frame < MAX_FRAMES && still < 10; frame += 1) {
    world.step(STEP);
    frames.push(bodies.flatMap((body) => [...body.position.toArray(), ...body.quaternion.toArray()]));
    const quiet = bodies.every((body) => body.velocity.length() < 0.05 && body.angularVelocity.length() < 0.1);
    still = quiet ? still + 1 : 0;
  }
  const rests = bodies.map((body): Quat => {
    const q: Quaternion = body.quaternion;
    return [q.x, q.y, q.z, q.w];
  });
  return { kinds, seed, frames, rests, settled: still >= 10 && flat(kinds, rests) };
}
