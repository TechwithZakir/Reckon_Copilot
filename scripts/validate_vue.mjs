import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { compileScript, compileTemplate, parse } from "@vue/compiler-sfc";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../reckon_copilot/public/js/copilot",
);

for (const name of fs.readdirSync(root).filter((file) => file.endsWith(".vue"))) {
  const filename = path.join(root, name);
  const source = fs.readFileSync(filename, "utf8");
  const { descriptor, errors } = parse(source, { filename });
  if (errors.length) throw errors[0];

  if (descriptor.scriptSetup) {
    compileScript(descriptor, { id: filename });
  }
  if (descriptor.template) {
    const result = compileTemplate({
      id: filename,
      filename,
      source: descriptor.template.content,
    });
    if (result.errors.length) throw result.errors[0];
  }
}

console.log("Vue component compilation passed.");
