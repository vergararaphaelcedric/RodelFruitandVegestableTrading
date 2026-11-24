import { cpSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

const copies = [
  ["node_modules/bootstrap/dist/css/bootstrap.min.css", "static/vendor/bootstrap/bootstrap.min.css"],
  ["node_modules/bootstrap/dist/css/bootstrap.min.css.map", "static/vendor/bootstrap/bootstrap.min.css.map"],
  ["node_modules/bootstrap/dist/js/bootstrap.bundle.min.js", "static/vendor/bootstrap/bootstrap.bundle.min.js"],
  ["node_modules/bootstrap/dist/js/bootstrap.bundle.min.js.map", "static/vendor/bootstrap/bootstrap.bundle.min.js.map"],
  ["node_modules/bootstrap-icons/font/bootstrap-icons.min.css", "static/vendor/bootstrap-icons/bootstrap-icons.min.css"],
  ["node_modules/bootstrap-icons/font/fonts", "static/vendor/bootstrap-icons/fonts"],
];

for (const [src, dest] of copies) {
  mkdirSync(dirname(dest), { recursive: true });
  cpSync(src, dest, { recursive: true });
}

console.log("Vendor files copied.");