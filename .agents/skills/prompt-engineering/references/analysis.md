# Task Analysis Framework

## Signal-Word Detection

Automatically detect what kind of prompt the user needs from their request:

| Signal Words | Detected Need | Recommended Action |
|---|---|---|
| "system prompt", "instructions for", "make a prompt" | New prompt from scratch | Full pipeline (Analyze → Architect → Generate → Refine) |
| "improve", "refine", "optimize", "fix", "better" | Improve existing prompt | Refinement meta-prompt |
| "agent", "bot", "assistant", "chatbot" | Agent system prompt | Agent meta-prompt |
| "tool", "API", "function calling", "search" | Tool-using agent | Tool-Using framework |
| "pipeline", "chain", "workflow", "multi-agent" | Pipeline agent | Pipeline Agent framework |
| "medical", "legal", "financial", "compliance" | Domain-specific | Domain Expert framework |
| "JSON", "structured", "schema", "classify" | Structured output | Emphasize Output Format section |
| "creative", "write", "story", "content" | Creative agent | COSTAR with style emphasis |
| "analyze", "research", "reason", "solve" | Reasoning agent | Multi-Step Reasoning framework |

## Task Decomposition

For complex agent descriptions, decompose into atomic requirements:

### Functional Requirements (What the agent DOES)
- Primary actions (verb list)
- Input types it handles
- Output types it produces
- Tools it needs to use

### Non-Functional Requirements (HOW the agent behaves)
- Response time expectations
- Tone and communication style
- Safety and compliance constraints
- Accuracy vs. creativity tradeoff
- Context window management

### Boundary Requirements (What the agent does NOT do)
- Explicit out-of-scope topics
- Actions that require human approval
- Information it must not disclose
- Domains it should redirect away from

## Audience Analysis Matrix

| Audience | Language Level | Detail Level | Tone | Format Preference |
|---|---|---|---|---|
| Executives | High-level, no jargon | Summary only | Confident, decisive | Bullet points, dashboards |
| Developers | Technical, precise | Full detail | Direct, collegial | Code examples, JSON |
| End Users | Plain language | Moderate | Friendly, patient | Conversational, step-by-step |
| Analysts | Data-literate | Deep detail | Professional | Tables, charts, methodology |
| Children / Students | Simple vocabulary | Scaffolded | Encouraging, fun | Visual, interactive |

## Constraint Extraction Checklist

When analyzing requirements, explicitly check for:

- [ ] **Token budget**: Is there a max response length?
- [ ] **Latency**: Does the agent need to respond in real-time?
- [ ] **Cost**: Should the agent minimize API calls / tool usage?
- [ ] **Safety**: Are there regulatory or compliance requirements?
- [ ] **Determinism**: Does the same input need to produce the same output?
- [ ] **Language**: Multi-language support needed?
- [ ] **Memory**: Does the agent need to remember across conversations?
- [ ] **Fallback**: What happens when the agent can't answer?
