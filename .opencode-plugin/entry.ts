/**
 * Engram — Combined V1+V2 Entrypoint
 * ===================================
 *
 * The single module behind `main`, `exports["."]`, and `exports["./server"]`.
 *
 * Why one module must satisfy both runtimes (issue #19): OpenCode 1.x
 * resolves npm plugin entries via resolvePackageEntrypoint, which probes
 * exports["./server"] FIRST and falls back to `main` only when that key is
 * absent (packages/opencode/src/plugin/shared.ts, shipping since Mar 2026).
 * OpenCode 2.x resolves the same package with import.meta.resolve on the
 * bare name — exports["."] — on its current line, and probed ./server on the
 * earlier next line. Every probe chain in the wild therefore lands on
 * whatever ./server or . points at, so pointing them at runtime-specific
 * files (V1 → index.ts, V2 → v2.ts) cannot work: V1 loaded the V2 adapter
 * and died on "must default export an object with server()".
 *
 * Both validators tolerate the union shape (verified against the sources):
 *
 *   V1 readV1Plugin      — requires default.server to be a function, rejects
 *                          only a server+tui pair, ignores unknown keys.
 *   V2 PluginModule      — requires default.id (string) and default.setup
 *     (Schema.decodeUnknown)  (function), ignores unknown keys.
 *
 * So `{ id, server, setup }` loads under every line: V1 calls server() and
 * never looks at setup; V2 calls setup() and never looks at server. The
 * runtime-specific modules stay importable directly (tests, the ./v2
 * subpath, local-checkout configs pointing at v2.ts).
 */

import { server } from "./index.js"
import { setup } from "./v2.js"

export { server, setup }

export default {
  id: "engram",
  server,
  setup,
}
