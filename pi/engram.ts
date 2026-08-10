/**
 * Engram — Pi extension (https://pi.dev)
 *
 * Two jobs, both ambient:
 *
 * 1. ENGRAM_ROOT — export the package root into pi's process env so the
 *    skills' engine-resolution block finds `scripts/engram.py` from any
 *    bash call, wherever the package was installed (git, npm, local path).
 *
 * 2. The nudge — once per session start (startup / new / resume), run
 *    `engram.py session-start`; if reviews are due, show one TUI notice
 *    and inject one custom message on the next user prompt so the model
 *    sees the same fact the human does.
 *
 * Contract (Constitution art. 8): ambient, never nagging — at most one
 * nudge per session, and on ANY failure degrade to silence, never to
 * repetition. Every handler is wrapped; nothing here may crash pi.
 *
 * Spawned children (the blind assessor et al. — see
 * skills/_shared/subagents.md) run with ENGRAM_CHILD=1 and without a UI
 * (`ctx.hasUI` is false in `-p` and `--mode json`): either condition makes
 * this extension inert, so a grader's context is never polluted by a nudge.
 *
 * Types below are structural on purpose. A type-only import of
 * @earendil-works/pi-coding-agent would drag pi into this package's
 * dependency graph, which also serves OpenCode users who must not install
 * pi's tree. The shape is checked against pi 0.74.x.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

type ExecResult = { stdout: string; stderr: string; code: number | null; killed?: boolean };

interface SessionStartEvent {
	type: "session_start";
	reason: "startup" | "reload" | "new" | "resume" | "fork";
}

interface BeforeAgentStartResult {
	message?: { customType: string; content: string; display: boolean };
}

interface Ctx {
	hasUI: boolean;
	ui: { notify(text: string, level?: "info" | "warning" | "error"): void };
}

interface PiLike {
	exec(command: string, args: string[], options?: { timeout?: number }): Promise<ExecResult>;
	on(event: "session_start", handler: (ev: SessionStartEvent, ctx: Ctx) => void | Promise<void>): void;
	on(
		event: "before_agent_start",
		handler: (ev: unknown, ctx: Ctx) => BeforeAgentStartResult | undefined,
	): void;
}

/** Directory of this file — jiti (pi's loader) provides import.meta.url; keep a CJS fallback. */
function selfDir(): string | null {
	try {
		return path.dirname(fileURLToPath(import.meta.url));
	} catch {
		/* fall through */
	}
	try {
		// @ts-ignore — defined when the loader transpiled us to CJS
		if (typeof __dirname === "string") return __dirname;
	} catch {
		/* fall through */
	}
	return null;
}

export default function engramExtension(pi: PiLike) {
	const dir = selfDir();
	const root = dir ? path.dirname(dir) : null; // this file lives at <root>/pi/engram.ts
	const engine = root ? path.join(root, "scripts", "engram.py") : null;
	const usable = !!(engine && fs.existsSync(engine));

	if (usable && !process.env.ENGRAM_ROOT) {
		process.env.ENGRAM_ROOT = root!;
	}

	let pending: string | null = null;
	let probeGen = 0;

	// Deliberately NOT async and nothing awaited: pi awaits session_start handlers
	// before rendering the TUI and before completing /new and /resume, so an awaited
	// exec here would freeze startup for up to the full timeout when the engine is
	// slow (cold NFS home, macOS python3 stub). Fire the probe and let the result
	// land whenever it lands — before_agent_start tolerates late or absent `pending`
	// (worst case the nudge rides the second prompt instead of the first).
	pi.on("session_start", (ev, ctx) => {
		try {
			if (!usable || !ctx.hasUI || process.env.ENGRAM_CHILD) return;
			// reload included: pi re-instantiates the extension on /reload, so an
			// announced-but-unconsumed nudge would otherwise vanish with the old
			// instance. Re-probing keeps it one-nudge-per-runtime by construction.
			if (ev.reason !== "startup" && ev.reason !== "new" && ev.reason !== "resume" && ev.reason !== "reload")
				return;
			// A nudge never crosses a session boundary, and a superseded probe never
			// lands. (Defensive: pi already re-instantiates extensions per session, so
			// both are unreachable today — but the invariant should hold locally, not
			// lean on the host's lifecycle promise.)
			pending = null;
			const gen = ++probeGen;
			void pi
				.exec("python3", [engine!, "session-start"], { timeout: 15000 })
				.then((res) => {
					if (gen !== probeGen) return; // a newer session start owns `pending` now
					// A timed-out/signal-killed child resolves code 0 with killed=true —
					// and possibly a truncated stdout fragment. Silence, never a torn nudge.
					const out = res.code === 0 && !res.killed ? res.stdout.trim() : "";
					if (!out) return; // nothing due — total silence
					pending = out;
					try {
						ctx.ui.notify(out.split("\n")[0].slice(0, 120), "info");
					} catch {
						/* notice is best-effort; the injected message below still lands */
					}
				})
				.catch(() => {
					if (gen === probeGen) pending = null; // silence over repetition
				});
		} catch {
			pending = null;
		}
	});

	pi.on("before_agent_start", (_ev, ctx) => {
		try {
			if (!pending || !ctx.hasUI || process.env.ENGRAM_CHILD) return undefined;
			const content = pending;
			pending = null; // one nudge per session, consumed on the first prompt
			return { message: { customType: "engram-nudge", content, display: true } };
		} catch {
			return undefined;
		}
	});
}
