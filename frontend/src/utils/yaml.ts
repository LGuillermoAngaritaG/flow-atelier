import type { Conduit } from "@/types/conduit";

export function renderConduitYaml(c: Conduit): string {
  const lines: string[] = [];
  lines.push(`name: ${c.name}`);
  lines.push(`description: ${JSON.stringify(c.description)}`);
  if (c.timeout) lines.push(`timeout: ${c.timeout}`);
  if (c.maxConcurrency) lines.push(`max_concurrency: ${c.maxConcurrency}`);
  lines.push(`inputs:`);
  for (const [key, hint] of Object.entries(c.inputs)) {
    lines.push(`  ${key}: ${JSON.stringify(hint)}`);
  }
  lines.push(`tasks:`);
  for (const t of c.tasks) {
    lines.push(`  - name: ${t.name}`);
    lines.push(`    tool: ${t.tool}`);
    lines.push(`    description: ${JSON.stringify(t.description)}`);
    lines.push(`    task: ${JSON.stringify(t.task)}`);
    if (t.dependsOn.length > 0) {
      lines.push(`    depends_on: [${t.dependsOn.join(", ")}]`);
    }
    if (t.conditionalOn) {
      lines.push(
        `    conditional_on: { task: ${t.conditionalOn.task}, ${t.conditionalOn.kind}: ${JSON.stringify(
          t.conditionalOn.pattern,
        )} }`,
      );
    }
    if (t.repeat) lines.push(`    repeat: ${t.repeat}`);
    if (t.interactive) lines.push(`    interactive: true`);
    if (t.inputs && Object.keys(t.inputs).length > 0) {
      lines.push(`    inputs:`);
      for (const [key, val] of Object.entries(t.inputs)) {
        lines.push(`      ${key}: ${JSON.stringify(val)}`);
      }
    }
  }
  return lines.join("\n");
}
