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

for (const registrationYear of [2012, 2026]) {
  test(`loaded profiles show all years since registration in ${registrationYear}`, () => {
    const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
    const original = resource.useResource;
    const { ToastProvider } = loadTypeScript(
      resolve(root, "components/ui/toast.tsx"),
    );
    const { PublicProfile } = loadTypeScript(
      resolve(root, "features/profile/public-profile.tsx"),
    );
    const avatar = "/api/v1/avatars/hackandcode/avatar-hash.png";
    resource.useResource = () => ({
      loading: false,
      error: "",
      data: {
        username: "hackandcode",
        display_name: "Hack and Code",
        avatar_url: avatar,
        bio: "Building Forge",
        company: "",
        location: "",
        website: "",
        public_email: null,
        social_links: [],
        created_at: `${registrationYear}-01-01T00:00:00Z`,
        repository_count: 0,
        repositories: [],
        activity: {
          year: 2026,
          available_years: Array.from(
            { length: 2026 - registrationYear + 1 },
            (_, index) => registrationYear + index,
          ),
          total: 5,
          private_total: 3,
          longest_streak: 1,
          incomplete: false,
          days: [{ date: "2026-01-01", count: 5, private_count: 3 }],
          totals: {
            commits: 2,
            repositories: 0,
            issues: 0,
            pulls: 0,
            comments: 0,
          },
        },
      },
    });
    try {
      const markup = renderToStaticMarkup(
        React.createElement(
          ToastProvider,
          null,
          React.createElement(PublicProfile, { username: "hackandcode" }),
        ),
      );
      assert.ok(markup.includes(`src="${avatar}"`));
      assert.match(markup, /3 private contributions/);
      assert.match(markup, /5 contributions on 2026-01-01 \(3 private\)/);
      assert.match(markup, /Public and private contributions/);
      const select = markup.match(
        /<select[^>]*aria-label="Contribution year"[\s\S]*?<\/select>/,
      )?.[0];
      assert.ok(select);
      const options = [...select.matchAll(/<option[^>]*value="(\d+)"/g)].map(
        (match) => Number(match[1]),
      );
      assert.deepEqual(
        options,
        Array.from(
          { length: 2026 - registrationYear + 1 },
          (_, index) => registrationYear + index,
        ),
      );
      assert.match(
        select,
        /<option(?=[^>]*value="2026")(?=[^>]*selected="")[^>]*>/,
      );
    } finally {
      resource.useResource = original;
    }
  });
}

test("the profile editor renders image upload and removal beside profile fields", () => {
  const auth = loadTypeScript(resolve(root, "features/auth/auth-context.tsx"));
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const originalAuth = auth.useAuth;
  const originalUpdate = auth.useUpdateAuth;
  const originalResource = resource.useResource;
  const { ToastProvider } = loadTypeScript(
    resolve(root, "components/ui/toast.tsx"),
  );
  const { ProfileEditor } = loadTypeScript(
    resolve(root, "features/profile/profile-editor.tsx"),
  );
  const profile = {
    username: "hackandcode",
    display_name: "Hack and Code",
    avatar_url: "/api/v1/avatars/hackandcode/hash.png",
    email: "account@example.com",
    bio: "",
    company: "",
    location: "",
    website: "",
    public_email: null,
    social_links: [],
  };
  auth.useAuth = () => profile;
  auth.useUpdateAuth = () => () => {};
  resource.useResource = () => ({ loading: false, error: "", data: profile });
  try {
    const markup = renderToStaticMarkup(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(ProfileEditor),
      ),
    );
    assert.match(markup, /type="file"/);
    assert.match(markup, /accept="image\/png,image\/jpeg,image\/webp"/);
    assert.match(markup, /Replace picture/);
    assert.match(markup, /Remove picture/);
    assert.match(markup, /Save public profile/);
    assert.match(markup, /href="\/u\/hackandcode"/);
  } finally {
    auth.useAuth = originalAuth;
    auth.useUpdateAuth = originalUpdate;
    resource.useResource = originalResource;
  }
});
