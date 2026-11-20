// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * One declaration per resource of how each API field is stored: its column, and how it is
 * written and read (JSON text for lists and objects, as SQLite has no arrays). The lite records
 * (vttRecords.ts) build their Prisma writes and their answers from it, so a field is named once
 * instead of in every insert, update and serialiser.
 */

export interface Column {
  /** The Prisma field. */
  column: string;
  write(value: unknown): unknown;
  read(stored: unknown): unknown;
}

/** A field stored as itself (text, numbers, booleans, nullable values). */
export function plain(column: string): Column {
  return { column, write: (value) => value, read: (stored) => stored };
}

function parseJson(stored: unknown, fallback: unknown): unknown {
  if (typeof stored !== 'string') return fallback;
  try {
    return JSON.parse(stored) as unknown;
  } catch {
    return fallback;
  }
}

/** A list stored as JSON text; unreadable text reads as an empty list. */
export function jsonList(column: string): Column {
  return {
    column,
    write: (value) => JSON.stringify(value),
    read: (stored) => {
      const value = parseJson(stored, []);
      return Array.isArray(value) ? value : [];
    },
  };
}

/** An object stored as JSON text; unreadable text reads as an empty object. */
export function jsonObject(column: string): Column {
  return {
    column,
    write: (value) => JSON.stringify(value),
    read: (stored) => {
      const value = parseJson(stored, {});
      return typeof value === 'object' && value !== null && !Array.isArray(value) ? value : {};
    },
  };
}

export type Columns = Readonly<Record<string, Column>>;

/** The Prisma data for the fields `input` names (an absent field is left as it is). */
export function columnsOf(columns: Columns, input: object): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  for (const [field, value] of Object.entries(input)) {
    const column = columns[field];
    if (column !== undefined && value !== undefined) data[column.column] = column.write(value);
  }
  return data;
}

/** A row's API fields, read back through their columns. */
export function fieldsOf(columns: Columns, row: object): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  for (const [field, column] of Object.entries(columns)) {
    fields[field] = column.read(Reflect.get(row, column.column));
  }
  return fields;
}
