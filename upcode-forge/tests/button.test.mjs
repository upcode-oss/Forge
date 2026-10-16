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

test("the public profile route renders public navigation and its loading state", () => {
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
  assert.match(markup, /href="\/login"/);
  assert.match(markup, /href="\/explore\/repositories"/);
  assert.match(markup, /Sign in/);
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
        organizations: [
          {
            id: 1,
            slug: "upcode",
            name: "Upcode",
            visibility: "public",
            avatar_url: "/api/v1/organizations/upcode/avatar/hash.png",
          },
        ],
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
      assert.match(markup, /href="\/o\/upcode"/);
      assert.match(markup, /aria-label="Upcode"/);
      assert.match(
        markup,
        /src="\/api\/v1\/organizations\/upcode\/avatar\/hash.png"/,
      );
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

const organization = {
  id: 1,
  slug: "upcode",
  name: "Upcode",
  description: "Build together",
  visibility: "private",
  avatar_url: "/api/v1/organizations/upcode/avatar/hash.png",
  role: "owner",
  member_count: 3,
  created_at: "2026-01-01T00:00:00Z",
  contact_email: "team@example.com",
  social_links: [{ label: "GitHub", url: "https://github.com/upcode" }],
};

test("workspace organization pages render separate profile and upload forms for editors", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const auth = loadTypeScript(resolve(root, "features/auth/auth-context.tsx"));
  const originalResource = resource.useResource;
  const originalAuth = auth.useAuth;
  const { ToastProvider } = loadTypeScript(
    resolve(root, "components/ui/toast.tsx"),
  );
  const { OrganizationWorkspace } = loadTypeScript(
    resolve(root, "features/organizations/organization-pages.tsx"),
  );
  const { AppRouterContext } = createRequire(import.meta.url)(
    "next/dist/shared/lib/app-router-context.shared-runtime",
  );
  auth.useAuth = () => ({ username: "admin" });
  try {
    for (const role of ["owner", "maintainer", "reader"]) {
      resource.useResource = (path) => ({
        loading: false,
        error: "",
        reload() {},
        data: path.endsWith("/members")
          ? [
              {
                username: "admin",
                display_name: "Admin",
                role,
                avatar_url: null,
              },
            ]
          : { ...organization, role },
      });
      const markup = renderToStaticMarkup(
        React.createElement(
          AppRouterContext.Provider,
          { value: { push() {} } },
          React.createElement(
            ToastProvider,
            null,
            React.createElement(OrganizationWorkspace, { slug: "upcode" }),
          ),
        ),
      );
      assert.equal(markup.includes('type="file"'), role !== "reader");
      assert.equal(markup.includes("Save organization"), role !== "reader");
      assert.equal(markup.includes("Delete organization"), role === "owner");
      assert.equal(markup.includes("New repository"), role !== "reader");
      assert.equal(markup.includes("Import repository"), role !== "reader");
      assert.match(markup, /href="\/o\/upcode"/);
      let depth = 0;
      for (const tag of markup.matchAll(/<\/?form\b/g)) {
        depth += tag[0].startsWith("</") ? -1 : 1;
        assert.ok(depth >= 0 && depth <= 1, "forms must not be nested");
      }
      assert.equal(depth, 0);
    }
  } finally {
    resource.useResource = originalResource;
    auth.useAuth = originalAuth;
  }
});

test("organization discovery uses the public search endpoint and links to profiles", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const original = resource.useResource;
  const { OrganizationList } = loadTypeScript(
    resolve(root, "features/organizations/organization-list.tsx"),
  );
  resource.useResource = (path) => {
    assert.match(path, /scope=public&q=Forge%20Team/);
    return {
      loading: false,
      error: "",
      reload() {},
      data: {
        items: [{ ...organization, visibility: "public", role: null }],
        total: 1,
      },
    };
  };
  try {
    const markup = renderToStaticMarkup(
      React.createElement(OrganizationList, { initialQuery: "Forge Team" }),
    );
    assert.match(markup, /role="search"/);
    assert.match(markup, /href="\/o\/upcode"/);
    assert.match(markup, /Build together/);
  } finally {
    resource.useResource = original;
  }
});

test("organization forms restrict visibility changes to Owners and keep avatar uploads separate", () => {
  const { OrganizationForm } = loadTypeScript(
    resolve(root, "features/organizations/organization-form.tsx"),
  );
  for (const role of ["owner", "maintainer"]) {
    const markup = renderToStaticMarkup(
      React.createElement(OrganizationForm, {
        organization: { ...organization, role },
        onSaved() {},
      }),
    );
    const select = markup.match(/<select[^>]*name="visibility"[^>]*>/)?.[0];
    assert.ok(select);
    assert.equal(select.includes('disabled=""'), role === "maintainer");
    assert.match(markup, /team@example.com/);
    assert.match(markup, /https:\/\/github.com\/upcode/);
    assert.doesNotMatch(markup, /type="file"/);
    assert.equal((markup.match(/<form\b/g) ?? []).length, 1);
  }
  const create = renderToStaticMarkup(
    React.createElement(OrganizationForm, { onSaved() {} }),
  );
  assert.match(create, /name="slug"/);
  assert.match(create, /value="private" selected=""/);
  assert.match(create, /Create organization/);
});

test("repository owner controls offer personal and manageable organization owners", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const original = resource.useResource;
  const { RepositoryOwnerFields } = loadTypeScript(
    resolve(root, "features/repositories/repository-owner-fields.tsx"),
  );
  resource.useResource = (path) => {
    assert.equal(path, "/repository-owners");
    return {
      loading: false,
      error: "",
      reload() {},
      data: {
        username: "admin",
        organizations: [
          { slug: "upcode", name: "Upcode", visibility: "public" },
        ],
      },
    };
  };
  try {
    const markup = renderToStaticMarkup(
      React.createElement(RepositoryOwnerFields),
    );
    assert.match(markup, /name="organization"/);
    assert.match(markup, /admin \(your account\)/);
    assert.match(markup, /value="upcode"/);
    assert.match(markup, /value="public"/);
  } finally {
    resource.useResource = original;
  }
});

for (const visibility of ["private", "public"]) {
  test(`repository owner controls keep a fixed ${visibility} organization and constrain visibility`, () => {
    const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
    const original = resource.useResource;
    const { RepositoryOwnerFields } = loadTypeScript(
      resolve(root, "features/repositories/repository-owner-fields.tsx"),
    );
    resource.useResource = (path) => {
      assert.equal(path, null);
      return { loading: false, error: "", data: null };
    };
    try {
      const markup = renderToStaticMarkup(
        React.createElement(RepositoryOwnerFields, {
          organization: { ...organization, visibility },
        }),
      );
      assert.match(markup, /type="hidden" name="organization" value="upcode"/);
      assert.equal(markup.includes('value="public"'), visibility === "public");
      assert.match(markup, /value="private" selected=""/);
    } finally {
      resource.useResource = original;
    }
  });
}

test("organization repositories render clone URLs and keep Reader actions read only", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const original = resource.useResource;
  const { ToastProvider } = loadTypeScript(
    resolve(root, "components/ui/toast.tsx"),
  );
  const { OrganizationRepositories } = loadTypeScript(
    resolve(root, "features/organizations/organization-repositories.tsx"),
  );
  resource.useResource = (path) => {
    assert.match(path, /^\/organizations\/upcode\/repositories\?/);
    return {
      loading: false,
      error: "",
      reload() {},
      data: {
        total: 1,
        items: [
          {
            id: 42,
            name: "project",
            owner: "upcode",
            description: "Our project",
            visibility: "private",
            default_branch: "main",
            created_at: "2026-01-01T00:00:00Z",
            clone_url:
              "https://forge.example/git/organizations/upcode/project.git",
            ssh_clone_url:
              "ssh://git@forge.example:2222/organizations/upcode/project.git",
          },
        ],
      },
    };
  };
  try {
    const markup = renderToStaticMarkup(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(OrganizationRepositories, {
          organization: { ...organization, role: "reader" },
        }),
      ),
    );
    assert.match(markup, /href="\/repositories\/42"/);
    assert.match(
      markup,
      /https:\/\/forge.example\/git\/organizations\/upcode\/project.git/,
    );
    assert.match(markup, /value="ssh"/);
    assert.doesNotMatch(markup, /New repository|Import repository/);
    assert.match(markup, /Your organization role grants read access/);
  } finally {
    resource.useResource = original;
  }
});

test("repository deletion is offered only to users with Maintain access", () => {
  const { ToastProvider } = loadTypeScript(
    resolve(root, "components/ui/toast.tsx"),
  );
  const { DeleteRepositoryCard } = loadTypeScript(
    resolve(root, "features/repositories/delete-repository-card.tsx"),
  );
  const { AppRouterContext } = createRequire(import.meta.url)(
    "next/dist/shared/lib/app-router-context.shared-runtime",
  );
  for (const owner_type of ["user", "organization"]) {
    for (const role of ["read", "write", "maintain"]) {
      const markup = renderToStaticMarkup(
        React.createElement(
          AppRouterContext.Provider,
          { value: { replace() {}, refresh() {} } },
          React.createElement(
            ToastProvider,
            null,
            React.createElement(DeleteRepositoryCard, {
              repo: {
                id: 42,
                owner: "upcode",
                name: "project",
                owner_type,
                owner_profile_url:
                  owner_type === "user" ? "/u/upcode" : "/o/upcode",
                role,
              },
            }),
          ),
        ),
      );
      assert.equal(markup.includes("Delete repository"), role === "maintain");
      if (role === "maintain") {
        assert.match(markup, /This cannot be undone/);
        assert.match(markup, /Git history, issues, pull requests, comments/);
        assert.match(markup, /button-destructive/);
      }
    }
  }
});

test("public registration, login and navigation follow the instance registration setting", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const original = resource.useResource;
  const { PublicHeader } = loadTypeScript(
    resolve(root, "components/public-header.tsx"),
  );
  const { default: Register } = loadTypeScript(
    resolve(root, "app/register/page.tsx"),
  );
  const { default: Login } = loadTypeScript(
    resolve(root, "app/login/page.tsx"),
  );
  const { AppRouterContext } = createRequire(import.meta.url)(
    "next/dist/shared/lib/app-router-context.shared-runtime",
  );
  try {
    for (const registration_enabled of [false, true]) {
      resource.useResource = (path) => ({
        loading: false,
        error: "",
        reload() {},
        data:
          path === "/instance"
            ? { name: "Test Forge", registration_enabled }
            : null,
      });
      const header = renderToStaticMarkup(React.createElement(PublicHeader));
      assert.match(header, /href="\/explore\/repositories"/);
      assert.match(header, /href="\/explore"/);
      assert.match(header, /href="\/login"/);
      assert.equal(header.includes('href="/register"'), registration_enabled);
      for (const Component of [Register, Login]) {
        const markup = renderToStaticMarkup(
          React.createElement(
            AppRouterContext.Provider,
            { value: { replace() {} } },
            React.createElement(Component),
          ),
        );
        if (Component === Register) {
          assert.equal(
            markup.includes('name="confirm_password"'),
            registration_enabled,
          );
          assert.equal(markup.includes('name="email"'), registration_enabled);
          assert.equal(
            markup.includes("Registration is closed"),
            !registration_enabled,
          );
          assert.doesNotMatch(markup, /name="is_admin"/);
        } else {
          assert.equal(
            markup.includes('href="/register"'),
            registration_enabled,
          );
        }
      }
    }
  } finally {
    resource.useResource = original;
  }
});

test("public repository discovery offers browsing without management actions", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const original = resource.useResource;
  const { RepositoryList } = loadTypeScript(
    resolve(root, "features/repositories/repository-list.tsx"),
  );
  resource.useResource = (path) => {
    assert.equal(path, "/repositories?scope=public");
    return {
      loading: false,
      error: "",
      data: [
        {
          id: 42,
          name: "project",
          owner: "upcode",
          owner_type: "organization",
          description: "Public project",
          visibility: "public",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    };
  };
  try {
    const markup = renderToStaticMarkup(
      React.createElement(RepositoryList, { publicOnly: true }),
    );
    assert.match(markup, /Explore repositories/);
    assert.match(markup, /href="\/repositories\/42"/);
    assert.doesNotMatch(
      markup,
      /New repository|Import repository|Filter visibility/,
    );
  } finally {
    resource.useResource = original;
  }
});

test("public repository pages render code and clone controls without write actions", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const original = resource.useResource;
  const { ToastProvider } = loadTypeScript(
    resolve(root, "components/ui/toast.tsx"),
  );
  const { RepositoryWorkspace } = loadTypeScript(
    resolve(root, "features/repositories/repository-workspace.tsx"),
  );
  try {
    for (const empty of [false, true]) {
      resource.useResource = (path) => ({
        loading: false,
        error: "",
        reload() {},
        data:
          path === "/repositories/42"
            ? {
                id: 42,
                name: "project",
                owner: "upcode",
                owner_type: "organization",
                owner_profile_url: "/o/upcode",
                description: "Public project",
                visibility: "public",
                role: "read",
                default_branch: "main",
                clone_url:
                  "https://forge.example/git/organizations/upcode/project.git",
                ssh_clone_url: null,
              }
            : path?.endsWith("/branches")
              ? empty
                ? []
                : ["main"]
              : path?.includes("/tree?")
                ? []
                : null,
      });
      const markup = renderToStaticMarkup(
        React.createElement(
          ToastProvider,
          null,
          React.createElement(RepositoryWorkspace, {
            id: "42",
            publicView: true,
          }),
        ),
      );
      assert.match(markup, /href="\/explore\/repositories"/);
      assert.match(markup, /href="\/o\/upcode"/);
      assert.match(markup, /Clone protocol/);
      assert.doesNotMatch(
        markup,
        /Delete repository|New issue|Merge pull request|git push|>Settings</,
      );
      if (empty) assert.match(markup, /No code has been pushed yet/);
    }
  } finally {
    resource.useResource = original;
  }
});

for (const role of [null, "reader", "maintainer", "owner"]) {
  test(`organization members expose controls appropriate to ${role ?? "public visitor"}`, () => {
    const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
    const original = resource.useResource;
    const { OrganizationMembers } = loadTypeScript(
      resolve(root, "features/organizations/organization-members.tsx"),
    );
    resource.useResource = () => ({
      loading: false,
      error: "",
      reload() {},
      data: [
        {
          username: "admin",
          display_name: "Admin",
          role: "owner",
          avatar_url: null,
        },
        {
          username: "alice",
          display_name: "Alice",
          role: "maintainer",
          avatar_url: null,
        },
        {
          username: "bob",
          display_name: "Bob",
          role: "reader",
          avatar_url: null,
        },
      ],
    });
    try {
      const markup = renderToStaticMarkup(
        React.createElement(OrganizationMembers, {
          slug: "upcode",
          role,
          username: role ? "bob" : undefined,
        }),
      );
      assert.match(markup, /href="\/u\/alice"/);
      assert.equal(
        markup.includes("Add member"),
        role === "owner" || role === "maintainer",
      );
      assert.equal(
        markup.includes('aria-label="Role for admin"'),
        role === "owner",
      );
      assert.equal(
        markup.includes('aria-label="Role for alice"'),
        role === "owner",
      );
      assert.equal(
        markup.includes('aria-label="Role for bob"'),
        role === "owner" || role === "maintainer",
      );
      assert.equal(markup.includes('aria-label="Leave organization"'), !!role);
      if (role === "maintainer")
        assert.doesNotMatch(markup, /<option[^>]*value="(?:owner|maintainer)"/);
      if (!role)
        assert.doesNotMatch(markup, /<form\b|Remove admin|Leave organization/);
    } finally {
      resource.useResource = original;
    }
  });
}

test("public organization profiles render contact details, pictures and member links", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const original = resource.useResource;
  const { PublicOrganization } = loadTypeScript(
    resolve(root, "features/organizations/organization-pages.tsx"),
  );
  resource.useResource = (path) => ({
    loading: false,
    error: "",
    reload() {},
    data: path.endsWith("/members")
      ? [
          {
            username: "admin",
            display_name: "Admin",
            role: "owner",
            avatar_url: null,
          },
        ]
      : { ...organization, visibility: "public", role: null },
  });
  try {
    const markup = renderToStaticMarkup(
      React.createElement(PublicOrganization, { slug: "upcode" }),
    );
    assert.match(markup, /mailto:team@example.com/);
    assert.match(markup, /href="https:\/\/github.com\/upcode"/);
    assert.match(
      markup,
      /src="\/api\/v1\/organizations\/upcode\/avatar\/hash.png"/,
    );
    assert.match(markup, /href="\/u\/admin"/);
    assert.match(markup, /href="\/explore"/);
    assert.doesNotMatch(markup, /Add member|Save organization|Your membership/);
  } finally {
    resource.useResource = original;
  }
});

test("repository clone controls show SSH URLs and hide SSH when disabled", () => {
  const { ToastProvider } = loadTypeScript(
    resolve(root, "components/ui/toast.tsx"),
  );
  const { CloneBar } = loadTypeScript(
    resolve(root, "features/repositories/clone-bar.tsx"),
  );
  const httpsUrl = "https://forge.example/git/alice/project.git";
  const sshUrl = "ssh://git@forge.example:2222/alice/project.git";
  function render(url) {
    return renderToStaticMarkup(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(CloneBar, {
          httpsUrl,
          sshUrl: url,
          protocol: "ssh",
          onProtocolChange: () => {},
        }),
      ),
    );
  }
  const enabled = render(sshUrl);
  assert.match(enabled, /aria-label="Clone protocol"/);
  assert.ok(enabled.includes(`<code>${sshUrl}</code>`));
  assert.match(
    enabled,
    /<option(?=[^>]*value="ssh")(?=[^>]*selected="")[^>]*>/,
  );
  const disabled = render(null);
  assert.ok(disabled.includes(`<code>${httpsUrl}</code>`));
  assert.doesNotMatch(disabled, /value="ssh"/);
});

test("SSH key settings render fingerprints, scopes and connection details", () => {
  const resource = loadTypeScript(resolve(root, "hooks/use-resource.ts"));
  const original = resource.useResource;
  const { ToastProvider } = loadTypeScript(
    resolve(root, "components/ui/toast.tsx"),
  );
  const { SSHKeysCard } = loadTypeScript(
    resolve(root, "features/profile/ssh-keys.tsx"),
  );
  resource.useResource = (path) => ({
    loading: false,
    error: "",
    data:
      path === "/ssh"
        ? {
            enabled: true,
            host: "forge.example",
            port: 2222,
            username: "git",
            host_fingerprint: "SHA256:server-key",
          }
        : [
            {
              id: 1,
              name: "Work laptop",
              fingerprint: "SHA256:user-key",
              scope: "read",
              created_at: "2026-01-01T00:00:00Z",
              last_used_at: null,
            },
          ],
  });
  try {
    const markup = renderToStaticMarkup(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(SSHKeysCard),
      ),
    );
    for (const text of [
      "Add SSH key",
      "Work laptop",
      "SHA256:user-key",
      "SHA256:server-key",
      "Read only",
      "git@forge.example",
      "Never",
    ]) {
      assert.ok(markup.includes(text), text);
    }
  } finally {
    resource.useResource = original;
  }
});
