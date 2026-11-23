// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { facesOf, readDown, relabel, rotate, upFace } from './faces';
import { MAX_FRAMES, seeded, simulateThrow, TRAY } from './simulate';

describe('a headless throw', () => {
  it('is the same tumble for the same seed, and another for another', () => {
    const one = simulateThrow(['d20', 'd6'], 42);
    expect(simulateThrow(['d20', 'd6'], 42).frames).toEqual(one.frames);
    expect(simulateThrow(['d20', 'd6'], 43).frames).not.toEqual(one.frames);
  });

  it.each([1, 2, 3, 4, 5, 6, 7, 8])('settles flat inside the tray, then shows the server value (seed %i)', (seed) => {
    const kinds = ['d10-tens', 'd10', 'd20', 'd6'] as const;
    const result = simulateThrow([...kinds], seed);
    expect(result.settled).toBe(true);
    expect(result.frames.length).toBeLessThanOrEqual(MAX_FRAMES);
    expect(result.seed - seed).toBeLessThan(6);
    const last = result.frames.at(-1)!;
    kinds.forEach((kind, die) => {
      const [x, y, z] = last.slice(die * 7, die * 7 + 3) as [number, number, number];
      expect(Math.abs(x)).toBeLessThan(TRAY[0]);
      expect(Math.abs(z)).toBeLessThan(TRAY[1]);
      expect(y).toBeGreaterThan(0);
      const faces = facesOf(kind);
      const face = upFace(faces, result.rests[die]!);
      // resting on a face, not cocked on an edge
      expect(rotate(faces.normals[face]!, result.rests[die]!)[1]).toBeGreaterThan(0.95);
      const wanted = faces.labels[(seed * 7) % faces.labels.length]!;
      const shown = relabel(faces, face, wanted);
      expect(shown.labels[upFace(shown, result.rests[die]!)]).toBe(wanted);
    });
  });

  it.each([1, 2, 3, 4])('settles a d4, d8 and d12 flat on a face (seed %i)', (seed) => {
    const kinds = ['d4', 'd8', 'd12'] as const;
    const result = simulateThrow([...kinds], seed);
    expect(result.settled).toBe(true);
    kinds.forEach((kind, die) => {
      const faces = facesOf(kind);
      const facing = rotate(faces.normals[upFace(faces, result.rests[die]!)]!, result.rests[die]!)[1];
      expect(readDown(kind) ? -facing : facing).toBeGreaterThan(0.95);
    });
  });

  it('draws from a seeded sequence in [0, 1)', () => {
    const draw = seeded(7);
    const values = Array.from({ length: 1000 }, draw);
    expect(Math.min(...values)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...values)).toBeLessThan(1);
    expect(seeded(7)()).toBe(values[0]);
  });
});
