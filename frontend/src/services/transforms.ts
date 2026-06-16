const SNAKE_RE = /_([a-z])/g;
const CAMEL_RE = /[A-Z]/g;

export function toCamelCase<T>(value: unknown): T {
  if (value === null || value === undefined) return value as T;
  if (typeof value !== "object") return value as T;
  if (Array.isArray(value)) return value.map(toCamelCase) as T;
  const obj = value as Record<string, unknown>;
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(obj)) {
    const camelKey = key.replace(SNAKE_RE, (_, c: string) => c.toUpperCase());
    result[camelKey] = toCamelCase(obj[key]);
  }
  return result as T;
}

export function toSnakeCase<T>(value: unknown): T {
  if (value === null || value === undefined) return value as T;
  if (typeof value !== "object") return value as T;
  if (Array.isArray(value)) return value.map(toSnakeCase) as T;
  const obj = value as Record<string, unknown>;
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(obj)) {
    const snakeKey = key.replace(CAMEL_RE, (c: string) => `_${c.toLowerCase()}`);
    result[snakeKey] = toSnakeCase(obj[key]);
  }
  return result as T;
}
