// Khronos glTF-Validator wrapper. Prints the JSON report for one file to stdout.
// Installed in the Docker image at /opt/gltf-validator (npm i gltf-validator).
import { readFile } from "node:fs/promises";
import validator from "gltf-validator";

const path = process.argv[2];
if (!path) {
  console.error("usage: node validate.mjs <file.glb>");
  process.exit(2);
}
const data = new Uint8Array(await readFile(path));
const report = await validator.validateBytes(data, { maxIssues: 50, externalResourceFunction: () =>
  Promise.reject(new Error("external resources are not allowed in Naqshkaar assets")) });
process.stdout.write(JSON.stringify(report));
