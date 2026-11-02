import { existsSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToReadableStream } from "react-dom/server";
import { describe, expect, it } from "vitest";
import catalog from "../../../public/avatars/catalog.json";
import { defaultAvatarId, agentAvatars, findAvatar } from "../../lib/avatars/registry";
import { AgentAvatar } from "./AgentAvatar";

const publicRoot = fileURLToPath(new URL("../../../public/", import.meta.url));

describe("current agent SVG portraits", () => {
  it("offers the thirteen approved color characters with stable agent role IDs", () => {
    expect(agentAvatars).toEqual(catalog.assets);
    expect(agentAvatars.map((avatar) => avatar.id).sort()).toEqual([
      "admin",
      "backend",
      "designer",
      "finance",
      "frontend",
      "intern",
      "knowledge",
      "operations",
      "product",
      "programmer",
      "research",
      "support",
      "sysadmin",
    ]);
    expect(defaultAvatarId).toBe("intern");
    expect(agentAvatars[0].id).toBe("intern");
    expect(findAvatar("intern-bull")?.id).toBe("intern");
    expect(findAvatar("backend-horse")?.id).toBe("backend");
    expect(findAvatar("frontend-bull")?.id).toBe("frontend");
    expect(findAvatar("designer")?.species).toBe("牛");
    expect(findAvatar("product")?.species).toBe("马");
    for (const asset of agentAvatars) {
      expect(asset.src).toMatch(/^\/avatars\/svg\/[a-z-]+\.svg$/);
      expect(existsSync(resolve(publicRoot, asset.src.slice(1)))).toBe(true);
    }
    expect(
      readdirSync(resolve(publicRoot, "avatars"))
        .filter((name) => !name.startsWith("."))
        .sort(),
    ).toEqual(["catalog.json", "svg"]);
  });

  it("keeps matching legacy selections and formal SVG IDs attached to their current role", () => {
    for (const [alias, role] of Object.entries(catalog.aliases)) {
      if (catalog.retiredIds.includes(role)) expect(findAvatar(alias)).toBeUndefined();
      else expect(findAvatar(alias)).toEqual(findAvatar(role));
    }
    expect(findAvatar("goofy-v5-company--cow-admin-goofy")?.id).toBe("admin");
    expect(findAvatar("designer-bull")?.id).toBe("designer");
    expect(findAvatar("goofy-v4--cow-operations-goofy")?.id).toBe("operations");
    expect(findAvatar("goofy-v5-company--horse-support-goofy")?.id).toBe("support");
  });

  it("renders the new SVG through the agent API for cards, navigation and conversations", async () => {
    for (const asset of agentAvatars) {
      const html = await avatarMarkup(
        createElement(AgentAvatar, {
          avatarId: asset.id,
          size: 48,
          alt: asset.name,
        }),
      );
      expect(html).toContain(`data-avatar-character="${asset.svgCharacter}"`);
      expect(html).toContain("<path");
      expect(html).not.toContain("data-avatar-loading");
      expect(html).toContain(`aria-label="${asset.name}"`);
      expect(html).toContain('data-avatar-renderer="svg"');
      expect(html).toContain('width="48" height="48"');
      expect(html).not.toMatch(/<img|<image|<canvas|\.webp|\.wasm/);
    }
  });

  it("uses a color display fallback without treating retired or unknown stored IDs as a new selection", async () => {
    for (const id of [...catalog.retiredIds, "goofy-v5-company--cow-hr-goofy", "missing-avatar"]) {
      expect(findAvatar(id)).toBeUndefined();
      const html = await avatarMarkup(createElement(AgentAvatar, { avatarId: id }));
      expect(html).toContain(`data-avatar-role="${defaultAvatarId}"`);
      expect(html).toContain('data-avatar-character="intern-bull"');
      expect(html).toContain('data-avatar-fallback="true"');
    }
  });
});

async function avatarMarkup(element: ReturnType<typeof createElement>) {
  const stream = await renderToReadableStream(element);
  await stream.allReady;
  return new Response(stream).text();
}
