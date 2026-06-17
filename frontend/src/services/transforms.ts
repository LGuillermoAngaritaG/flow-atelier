const SNAKE_RE = /_([a-z])/g;
const CAMEL_RE = /[A-Z]/g;

// Free-form maps whose KEYS are user-controlled (input field names, task names,
// arbitrary extra data). Their direct keys must cross the wire byte-identical;
// only their VALUES get key-converted. Both casings are listed so the guard
// works in either direction.
const OPAQUE_MAP_KEYS = new Set([
  "inputs",
  "answers",
  "hitlAnswers",
  "hitl_answers",
  "taskStatuses",
  "task_statuses",
  "extra",
]);

function snakeToCamel(key: string): string {
  return key.replace(SNAKE_RE, (_, c: string) => c.toUpperCase());
}

function camelToSnake(key: string): string {
  return key.replace(CAMEL_RE, (c: string) => `_${c.toLowerCase()}`);
}

function convert<T>(value: unknown, renameKey: (k: string) => string): T {
  if (value === null || value === undefined) return value as T;
  if (typeof value !== "object") return value as T;
  if (Array.isArray(value)) return value.map((v) => convert(v, renameKey)) as T;
  const obj = value as Record<string, unknown>;
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(obj)) {
    if (OPAQUE_MAP_KEYS.has(key)) {
      result[renameKey(key)] = convertOpaqueMap(obj[key], renameKey);
    } else {
      result[renameKey(key)] = convert(obj[key], renameKey);
    }
  }
  return result as T;
}

// Keep the map's own keys literal; still convert each value's inner structure
// (e.g. taskStatuses values are typed status objects with fixed field names).
function convertOpaqueMap(value: unknown, renameKey: (k: string) => string): unknown {
  if (value === null || value === undefined || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map((v) => convert(v, renameKey));
  const obj = value as Record<string, unknown>;
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(obj)) {
    result[key] = convert(obj[key], renameKey);
  }
  return result;
}

export function toCamelCase<T>(value: unknown): T {
  return convert<T>(value, snakeToCamel);
}

export function toSnakeCase<T>(value: unknown): T {
  return convert<T>(value, camelToSnake);
}
