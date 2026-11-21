// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { diceFor, facesOf, geometryOf, relabel, rotate, upFace, type DieKind, type Quat, type Vec3 } from './faces';

const KINDS: DieKind[] = ['d6', 'd10', 'd10-tens', 'd20'];

/** The rotation taking unit vector ``from`` onto +y. */
function toUp([x, y, z]: Vec3): Quat {
  const dot = y;
  if (dot > 1 - 1e-9) return [0, 0, 0, 1];
  if (dot < -1 + 1e-9) return [1, 0, 0, 0];
  // axis = from × up = (−z, 0, x) as (x, y, z) × (0, 1, 0)
  const axis: Vec3 = [-z, 0, x];
  const half = Math.acos(dot) / 2;
  const length = Math.hypot(...axis);
  const s = Math.sin(half) / length;
  return [axis[0] * s, axis[1] * s, axis[2] * s, Math.cos(half)];
}

describe('the dice', () => {
  it.each(KINDS)('a %s has one distinct unit normal per face', (kind) => {
    const faces = facesOf(kind);
    expect(faces.normals).toHaveLength(faces.labels.length);
    for (const normal of faces.normals) expect(Math.hypot(...normal)).toBeCloseTo(1, 9);
    const keys = new Set(faces.normals.map((normal) => normal.map((value) => value.toFixed(6)).join()));
    expect(keys.size).toBe(faces.normals.length);
  });

  it.each(KINDS)('a %s is a closed convex solid whose every face is flat', (kind) => {
    const { vertices, faces } = geometryOf(kind);
    const { normals } = facesOf(kind);
    expect(faces).toHaveLength(normals.length);
    faces.forEach((face, index) => {
      const normal = normals[index]!;
      const offsets = face.map((corner) => {
        const [x, y, z] = vertices[corner]!;
        return x * normal[0] + y * normal[1] + z * normal[2];
      });
      for (const offset of offsets) expect(offset).toBeCloseTo(offsets[0]!, 9);
      for (const [x, y, z] of vertices)
        expect(x * normal[0] + y * normal[1] + z * normal[2]).toBeLessThanOrEqual(offsets[0]! + 1e-9);
    });
    // Euler: V − E + F = 2
    const edges = new Set(
      faces.flatMap((face) => face.map((corner, i) => [corner, face[(i + 1) % face.length]!].sort().join())),
    );
    expect(vertices.length - edges.size + faces.length).toBe(2);
  });

  it.each(KINDS)('a %s resting on any face reads that face', (kind) => {
    const faces = facesOf(kind);
    faces.normals.forEach((normal, index) => {
      expect(rotate(normal, toUp(normal))[1]).toBeCloseTo(1, 9);
      expect(upFace(faces, toUp(normal))).toBe(index);
    });
  });

  it.each(KINDS)('a %s settled on any face can be made to show every value', (kind) => {
    const faces = facesOf(kind);
    faces.normals.forEach((normal, face) => {
      for (const label of faces.labels) {
        const shown = relabel(faces, face, label);
        expect(shown.labels[upFace(shown, toUp(normal))]).toBe(label);
        expect([...shown.labels].sort()).toEqual([...faces.labels].sort());
      }
    });
  });

  it('refuses a value the die does not have', () => {
    expect(() => relabel(facesOf('d6'), 0, '7')).toThrow('no face 7');
  });
});

describe('a server result as dice', () => {
  it('reads a d100 as tens and units, 100 as 00 and 0', () => {
    expect(diceFor(100, 47)).toEqual([
      { kind: 'd10-tens', label: '40' },
      { kind: 'd10', label: '7' },
    ]);
    expect(diceFor(100, 5)).toEqual([
      { kind: 'd10-tens', label: '00' },
      { kind: 'd10', label: '5' },
    ]);
    expect(diceFor(100, 100)).toEqual([
      { kind: 'd10-tens', label: '00' },
      { kind: 'd10', label: '0' },
    ]);
  });

  it('shows other sizes as themselves, a d10 of 10 as 0', () => {
    expect(diceFor(20, 17)).toEqual([{ kind: 'd20', label: '17' }]);
    expect(diceFor(6, 1)).toEqual([{ kind: 'd6', label: '1' }]);
    expect(diceFor(10, 10)).toEqual([{ kind: 'd10', label: '0' }]);
    expect(() => diceFor(8, 3)).toThrow('no 3D die');
  });
});
