"use strict";

const { spawnSync } = require("node:child_process");

const result = spawnSync("python3", ["-m", "unittest", "discover", "-s", "tests", "-v"], {
  cwd: __dirname,
  stdio: "inherit",
});
if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
