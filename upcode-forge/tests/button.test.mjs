import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { compileFunction } from "node:vm";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const root = fileURLToPath(new URL("../", import.meta.url));
const modules = new Map();

// Render the actual TSX components with their installed dependencies, without a browser or build.
function loadTypeScript(path) {
  const filename = [path, `${path}.ts`, `${path}.tsx`].find(existsSync);
  if (!filename) throw new Error(`Module not found: ${path}`);
  if (modules.has(filename)) return modules.get(filename).exports;
  const compiledModule = { exports: {} };
  modules.set(filename, compiledModule);
  const localRequire = createRequire(filename);
  const { outputText } = ts.transpileModule(readFileSync(filename, "utf8"), {
    fileName: filename,
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const require = (specifier) => {
    if (specifier.startsWith("@/"))
      return loadTypeScript(resolve(root, specifier.slice(2)));
    if (specifier.startsWith("."))
      return loadTypeScript(resolve(dirname(filename), specifier));
    return localRequire(specifier);
  };
  compileFunction(outputText, ["require", "module", "exports"], { filename })(
    require,
    compiledModule,
    compiledModule.exports,
  );
  return compiledModule.exports;
}

const { Button } = loadTypeScript(resolve(root, "components/ui/button.tsx"));

test("a button styled profile link renders as a single anchor", () => {
  const markup = renderToStaticMarkup(
    React.createElement(
      Button,
      { asChild: true, variant: "outline" },
      React.createElement("a", { href: "/u/hackandcode" }, "View profile"),
    ),
  );
  assert.match(markup, /^<a /);
  assert.match(markup, /href="\/u\/hackandcode"/);
  assert.match(markup, /button-outline/);
  assert.match(markup, />View profile<\/a>$/);
});

test("loading link buttons keep the spinner and label inside the anchor", () => {
  const markup = renderToStaticMarkup(
    React.createElement(
      Button,
      { asChild: true, loading: true },
      React.createElement("a", { href: "/profile" }, "Saving profile"),
    ),
  );
  assert.match(markup, /^<a /);
  assert.match(markup, /class="[^"]*spin/);
  assert.match(markup, /Saving profile<\/a>$/);
});

test("native loading buttons still disable submission and render their label", () => {
  const markup = renderToStaticMarkup(
    React.createElement(Button, { loading: true, type: "submit" }, "Save"),
  );
  assert.match(markup, /^<button /);
  assert.match(markup, /disabled=""/);
  assert.match(markup, /type="submit"/);
  assert.match(markup, /Save<\/button>$/);
});

test("the public profile route renders its workspace link and loading state", () => {
  const { ToastProvider } = loadTypeScript(
    resolve(root, "components/ui/toast.tsx"),
  );
  const { PublicProfile } = loadTypeScript(
    resolve(root, "features/profile/public-profile.tsx"),
  );
  const markup = renderToStaticMarkup(
    React.createElement(
      ToastProvider,
      null,
      React.createElement(PublicProfile, { username: "hackandcode" }),
    ),
  );
  assert.match(markup, /href="\/dashboard"/);
  assert.match(markup, /Open workspace/);
  assert.match(markup, /role="status"/);
  assert.match(markup, /Loading/);
});
