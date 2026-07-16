# How It Works

Agent Harness separates generic machinery from local project knowledge.

```mermaid
flowchart LR
  User["Human gives intent"] --> Agent["Claude Code / Codex / Cursor / opencode / pi"]
  Agent --> MCP["Harness MCP tools or CLI"]
  Agent -.-> Gates["Native hook gates (policy engine)"]
  MCP --> Runtime["Local runtime"]
  Runtime --> Packet["Task packet"]
  Runtime --> Worktree["Harness worktree"]
  Runtime --> Evidence["Evidence gate"]
  Runtime --> Memory["Local memory inbox"]
  Runtime --> Review["Review lanes + subagents"]
  Runtime --> Dashboard["Dashboard"]
```

## Gate Flow

Every tool surface routes risky actions through one policy engine, wired into that tool's native hook system at setup:

```mermaid
flowchart LR
  CC["Claude Code settings.json hooks"] --> Engine["pre-tool-policy.py"]
  Cur["Cursor hooks.json"] --> Bridge["cursor-bridge.py"] --> Engine
  OC["opencode plugin tool.execute.before"] --> Engine
  PI["pi extension tool_call"] --> Engine
  Engine --> Decision{"allow / ask / deny"}
  Decision -->|deny| Blocked["Blocked with reason fed back to the agent"]
  Decision -->|ask| Human["Human confirms"]
  Stop["Stop hook"] --> EvidenceGate["active task has passing evidence?"]
  EvidenceGate -->|no| BlockStop["Stop blocked: finish through evidence"]
```

`agent-harness verify-gates` pipes canned payloads through every hook and asserts the decision — the guardrails are tested behavior, not documentation.

## Runtime Architecture

```mermaid
flowchart TB
  Package["GitHub package via npx"] --> Setup["setup"]
  Setup --> SourceBundle["runtime/source/agent-harness"]
  Setup --> RuntimeFiles["runtime files"]
  Setup --> Profile["generated project profile"]
  Setup --> Shims["agent-harness / ah shims"]
  Setup --> Adapters["Managed app adapters"]
  Setup --> Snippets["Manual adapter snippets"]
  RuntimeFiles --> MCPServer["MCP server"]
  RuntimeFiles --> Hooks["hooks"]
  RuntimeFiles --> Skills["skills"]
  RuntimeFiles --> Templates["templates"]
```

The runtime source bundle makes installs independent from the temporary `npx` cache. After setup, the runtime launcher points at the copied bundle.

## App Discovery

```mermaid
flowchart LR
  Setup["setup"] --> Codex["Codex user instructions + MCP"]
  Setup --> Claude["Claude user memory + MCP"]
  Setup --> Cursor["Cursor local rule + MCP"]
  Setup --> Exclude[".git/info/exclude for repo-local adapter files"]
  Codex --> Agent["Agent opens in repo"]
  Claude --> Agent
  Cursor --> Agent
  Agent --> Harness["Harness MCP or shim fallback"]
```

The adapter layer is intentionally thin. It tells each agent surface that a harness exists, points it at the local MCP server, and instructs it to start or resume a task instead of asking the human for backend commands.

## Task Lifecycle

```mermaid
sequenceDiagram
  participant H as Human
  participant A as Agent
  participant M as Harness MCP
  participant R as Runtime
  H->>A: Natural-language task
  A->>M: start_task or resume_task
  M->>R: Write packet and status
  A->>M: create/use worktree when needed
  A->>A: Implement, inspect, test
  A->>M: review_plan and review_run for riskier work
  A->>M: write_evidence
  A->>M: evidence_doctor and finish_task
  M->>R: Update dashboard and artifacts
```

## PR Review Flow

```mermaid
flowchart TD
  PR["PR number, URL, or local branch"] --> Packet["PR review packet"]
  Packet --> Risk["Risk classifier"]
  Risk --> Context["Context packet"]
  Context --> Lanes["Selected specialist lanes"]
  Lanes --> Findings["Structured private findings"]
  Findings --> Coordinator["Coordinator filter"]
  Coordinator --> Draft["Public comments draft"]
  Draft --> Human["Human decides what to post"]
```

The PR flow is draft-only by default. It optimizes for fewer, better comments rather than more AI output.

## External Write Flow

```mermaid
sequenceDiagram
  participant H as Human
  participant A as Agent
  participant M as Harness
  participant C as Connector
  H->>A: Write/update a Confluence page
  A->>M: external_write_intent
  M-->>A: scoped intent id
  A->>C: connector-native write
  A->>C: read back or verify
  A->>M: record evidence
```

The harness does not export raw tokens. Writes use whatever connector-native auth the agent surface already provides.
