import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const { outputText } = ts.transpileModule(
  readFileSync(new URL("../lib/instance-link.ts", import.meta.url), "utf8"),
  {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  },
);
const { initialCallbackUrl } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

test("a default localhost callback uses the address actually opened in the browser", () => {
  for (const value of [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://[::1]:3000",
  ]) {
    assert.equal(
      initialCallbackUrl(value, "http://192.168.122.45:3001"),
      "http://192.168.122.45:3001",
    );
  }
});

test("the browser port is preserved when running two instances on localhost", () => {
  assert.equal(
    initialCallbackUrl("http://localhost:3000", "http://localhost:3001"),
    "http://localhost:3001",
  );
});

test("a configured public domain is preserved when browsing via a different address", () => {
  assert.equal(
    initialCallbackUrl(
      "https://sprint.example.com/",
      "http://192.168.122.45:3000",
    ),
    "https://sprint.example.com",
  );
});
