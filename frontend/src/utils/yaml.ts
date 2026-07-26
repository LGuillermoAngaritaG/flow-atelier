import type { Conduit } from "@/types/conduit";
import { formatDependency } from "@/utils/conditions";

// Plain scalars/keys that are safe to emit unquoted. Anything with YAML-special
// punctuation (`:`, `#`, etc.) is double-quoted via JSON.stringify so a name
// like `build: prod` or a field named `time #1` still produces parseable YAML.
const SAFE_SCALAR = /^[A-Za-z0-9_][A-Za-z0-9 ._-]*$/;

function yamlScalar(s: string): string {
  return SAFE_SCALAR.test(s) ? s : JSON.stringify(s);
}

export function renderConduitYaml(c: Conduit): string {
  const lines: string[] = [];
  lines.push(`name: ${yamlScalar(c.name)}`);
  lines.push(`description: ${JSON.stringify(c.description)}`);
  if (c.timeout) lines.push(`timeout: ${c.timeout}`);
  if (c.maxConcurrency) lines.push(`max_concurrency: ${c.maxConcurrency}`);
  lines.push(`inputs:`);
  for (const [key, hint] of Object.entries(c.inputs)) {
    lines.push(`  ${yamlScalar(key)}: ${JSON.stringify(hint)}`);
  }
  lines.push(`tasks:`);
  for (const t of c.tasks) {
    lines.push(`  - name: ${yamlScalar(t.name)}`);
    lines.push(`    tool: ${t.tool}`);
    lines.push(`    description: ${JSON.stringify(t.description)}`);
    lines.push(`    task: ${JSON.stringify(t.task)}`);
    if (t.dependsOn.length > 0) {
      // Conditions live inside the depends_on entries — there is no
      // `conditional_on` key in the conduit schema, so emitting one produced a
      // preview that the engine would silently ignore.
      const deps = t.dependsOn.map((dep) =>
        yamlScalar(formatDependency(dep, t.conditions?.[dep])),
      );
      lines.push(`    depends_on: [${deps.join(", ")}]`);
    }
    if (t.repeat) lines.push(`    repeat: ${t.repeat}`);
    if (t.interactive) lines.push(`    interactive: true`);
    if (t.inputs && Object.keys(t.inputs).length > 0) {
      lines.push(`    inputs:`);
      for (const [key, val] of Object.entries(t.inputs)) {
        lines.push(`      ${yamlScalar(key)}: ${JSON.stringify(val)}`);
      }
    }
  }
  return lines.join("\n");
}
