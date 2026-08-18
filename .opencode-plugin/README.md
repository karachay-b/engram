# Develop Engram Plugin

## Local setup

1. Clone the repo:

   ```bash
   git clone https://github.com/nagisanzenin/engram
   cd engram
   ```

2. Install dependencies:

   ```bash
   npm install
   ```

3. Create `opencode.json` in this repo (OpenCode accepts relative paths):

   ```bash
   cat > opencode.json <<EOF
   {
     "\$schema": "https://opencode.ai/config.json",
     "plugin": ["."]
   }
   EOF
   ```

## How it works

The package entry is the combined adapter `.opencode-plugin/entry.ts` — default export
`{ id, server, setup }` — behind `package.json`'s `"main"`, `exports["."]`, and
`exports["./server"]`. OpenCode 1.x calls `server()` (the V1 plugin in `index.ts`);
OpenCode 2.x calls `setup()` (the V2 adapter in `v2.ts`, also reachable directly via
`exports["./v2"]`). Both validators tolerate the other runtime's key — see `entry.ts`
for the analysis (issue #19). When OpenCode loads the plugin:

1. `server()` registers the tool, session hooks, and shell-env hooks (V1);
   `setup()` wires the equivalent V2 domains
2. `config()` runs `selfExtract()` — copies `skills/`, `agents/`, `scripts/`, `gold/`,
   `experiments/`, `docs/` (top-level) to `.opencode/` in the test project
3. On first execution, the bridge registers agents, commands, and skills via `cfg.*`
4. Subsequent sessions use OpenCode's native disk discovery

## Structure

| Path                | Purpose                                                               |
| --------------------|---------------------------------------------------------------------- |
| `.opencode-plugin/` | TypeScript source (entry, install, update, tools, agents)             |
| `hooks/`            | Session hooks (notifications, shell env)                              |
| `scripts/`          | Python engine (`engram.py`) and git filter scripts                    |
| `skills/`           | Skill definitions (learn, review, coach)                              |
| `agents/`           | Subagent definitions (assessor, curriculum-architect, artifact-smith) |
| `package.json`      | Npm manifest — `main`/`.`/`./server` → `entry.ts`, `./v2` → `v2.ts`   |
