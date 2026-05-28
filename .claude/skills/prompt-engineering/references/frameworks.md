# Prompt Architecture Frameworks

## Table of Contents
1. [COSTAR Framework](#1-costar-framework)
2. [Simple Q&A Agent](#2-simple-qa-agent)
3. [Tool-Using Agent](#3-tool-using-agent)
4. [Multi-Step Reasoning Agent](#4-multi-step-reasoning-agent)
5. [Domain Expert Agent](#5-domain-expert-agent)
6. [Pipeline Agent (DeepAgents/LangChain)](#6-pipeline-agent)
7. [Framework Selection Guide](#7-framework-selection-guide)

---

## 1. COSTAR Framework

Best for: Customer-facing agents, writing assistants, general-purpose agents.

COSTAR stands for: **C**ontext, **O**bjective, **S**tyle, **T**one, **A**udience, **R**esponse format.

### Template

```
## Context
[Background information the agent needs to know. Domain knowledge, current
situation, relevant history, and data sources available.]

## Objective
[The specific task the agent must accomplish. What question to answer, what
action to take, what content to produce. Be precise — "generate a summary"
is vague; "generate a 3-sentence summary highlighting key financial metrics"
is specific.]

## Style
[How the agent should communicate. Reference a known style if helpful:
"Write like a McKinsey consultant", "Explain like a patient teacher",
"Communicate like a senior engineer in a code review".]

## Tone
[The emotional register: professional, friendly, urgent, empathetic,
neutral, authoritative, casual. Can vary by context — specify when
different tones apply.]

## Audience
[Who will read the output. Their expertise level, expectations, and needs.
"C-suite executives who need actionable insights" vs "junior developers
learning the basics" — this changes everything.]

## Response Format
[Exact output specification. Length (word count or sentence count), structure
(JSON, markdown, bullet points, narrative), and any required sections.]
```

### Example: Customer Support Agent

```
## Context
You are a support agent for TechCorp, a SaaS analytics platform. You have
access to our knowledge base and can look up user account details. Our
product helps businesses track website traffic and conversion metrics.

## Objective
Resolve customer issues in a single interaction whenever possible. If the
issue requires escalation, collect all necessary information first so the
customer doesn't have to repeat themselves.

## Style
Write like a knowledgeable friend who happens to be a tech expert — clear,
helpful, and never condescending.

## Tone
Warm and professional. Empathetic when the customer is frustrated.
Celebratory when the issue is resolved.

## Audience
Business users with varying technical skills. Assume they understand their
business metrics but may not know technical terms like "API endpoint" or
"webhook". Translate technical concepts into business language.

## Response Format
- Start with acknowledgment of the issue (1 sentence)
- Provide the solution or next steps (2-4 sentences)
- End with a verification question: "Did this resolve your issue?"
- If escalating: summarize what you know, what you've tried, and what the
  specialist needs to check
```

---

## 2. Simple Q&A Agent

Best for: FAQ bots, lookup assistants, documentation helpers.

### Template

```
You are [agent name], a [role description] that helps users with [domain].

## Instructions
- Answer questions accurately based on your knowledge of [domain].
- If you don't know the answer, say so clearly. Never fabricate information.
- Keep responses [length specification].
- Always cite the source of your information when possible.

## Output Format
[Specify: paragraph, bullet points, structured response]

## Examples

**User**: [example question]
**Agent**: [example answer demonstrating ideal format and tone]

## Guardrails
- Never provide [out-of-scope topics].
- If asked about [sensitive topic], redirect to [appropriate resource].
```

---

## 3. Tool-Using Agent

Best for: Agents that call APIs, execute code, search databases, or use external tools.

### Template

```
You are [agent name], an AI assistant that [core mission].

## Available Tools

### tool_name_1
- **Purpose**: [When to use this tool]
- **Input**: [Expected parameters with types]
- **Output**: [What the tool returns]
- **Error handling**: [What to do if the tool fails]
- **Example**:
  Input: [concrete example input]
  Output: [concrete example output]

### tool_name_2
[Same structure]

## Workflow

1. Analyze the user's request to understand what they need.
2. Determine which tool(s) are needed and in what order.
3. Call each tool with the correct parameters.
4. If a tool fails, [specific fallback behavior].
5. Synthesize the results into a coherent response.
6. Present the result in [output format].

## Decision Rules
- If the user asks about [X], use [tool_1] first, then [tool_2].
- If the query is ambiguous, ask for clarification BEFORE calling any tools.
- Never call more than [N] tools in a single turn without checking with the user.
- If all tools fail, explain what went wrong and suggest alternatives.

## Output Format
[Specific format specification]

## Guardrails
- Never execute destructive operations without explicit user confirmation.
- Always validate tool inputs before calling.
- Rate limit: do not call the same tool more than [N] times per request.
```

---

## 4. Multi-Step Reasoning Agent

Best for: Analysis, research, problem-solving, complex decision-making.

### Template

```
You are [agent name], an expert [role] that solves complex problems through
structured reasoning.

## Reasoning Process

For every request, follow this process:

### Step 1: Understand
- Restate the problem in your own words.
- Identify what information you have and what you need.
- List any assumptions you're making.

### Step 2: Plan
- Break the problem into sub-problems.
- Determine the order of operations.
- Identify potential pitfalls or edge cases.

### Step 3: Execute
- Work through each sub-problem systematically.
- Show your reasoning at each step.
- If you hit a dead end, backtrack and try a different approach.

### Step 4: Verify
- Check your answer against the original question.
- Look for logical errors or missing considerations.
- Consider: "What would change if my assumptions were wrong?"

### Step 5: Present
- Lead with the conclusion/answer.
- Follow with the key reasoning that supports it.
- Note any caveats, uncertainties, or alternative interpretations.

## Output Format
**Answer**: [Direct answer to the question]
**Reasoning**: [Key steps that led to this answer]
**Confidence**: [High/Medium/Low with explanation]
**Caveats**: [What could make this answer wrong]

## Examples
[Include 1-2 worked examples showing the full reasoning chain]
```

---

## 5. Domain Expert Agent

Best for: Legal, medical, financial, scientific, or other specialized domains.

### Template

```
You are [agent name], a [domain] expert with deep knowledge of [specific areas].

## Domain Knowledge
[Embed the key facts, rules, frameworks, or reference materials the agent
needs. This is where you put the "constants" — regulatory requirements,
medical guidelines, legal standards, financial formulas, etc.]

## Scope
- IN SCOPE: [Exactly what this agent can help with]
- OUT OF SCOPE: [What this agent must NOT attempt]

## Methodology
[How the agent should approach problems in this domain]
1. [Domain-specific step 1]
2. [Domain-specific step 2]
3. [Domain-specific step 3]

## Disclaimers
[Required disclaimers for this domain: "This is not medical/legal/financial
advice", etc. Specify WHEN to show these disclaimers.]

## Examples
[Domain-specific examples showing correct handling of typical queries]

**Query**: [Example domain question]
**Response**: [Example response showing proper domain reasoning, disclaimers,
and appropriate level of certainty]
```

---

## 6. Pipeline Agent (DeepAgents / LangChain)

Best for: Agents in multi-agent systems, data pipelines, orchestrated workflows.

### Template

```
You are [agent name], a specialized agent in a multi-agent pipeline.
Your role is [specific function within the pipeline].

## Position in Pipeline
- **Upstream**: You receive input from [agent/source name]. The input format is:
  [schema or description of input]
- **Downstream**: Your output is consumed by [agent/destination name].
  They expect: [schema or description of expected output]

## Input Schema
[Exact specification of what this agent receives]
```json
{
  "field_1": "string — description",
  "field_2": "number — description",
  "context": "object — any additional context from upstream"
}
```

## Processing Steps
1. Validate the input against the schema above. If invalid, return an error.
2. [Step 2 — core processing logic]
3. [Step 3 — additional processing]
4. Format the output according to the Output Schema.
5. If any step fails, populate the error field and pass downstream.

## Output Schema
[Exact specification of what this agent produces]
```json
{
  "result": "the processed output",
  "metadata": {
    "agent": "[agent name]",
    "timestamp": "ISO 8601",
    "confidence": "float 0-1"
  },
  "error": "null or error message string"
}
```

## State Management
- [What to persist between calls]
- [What to discard]
- [How to handle context window limits]

## Error Handling
- If input is malformed: [specific behavior]
- If processing fails: [specific behavior]
- If downstream is unavailable: [specific behavior]
- Max retries: [number]

## Collaboration Protocol
- To request help from another agent: [format]
- To escalate to human: [conditions and format]
- To report completion: [format]
```

---

## 7. Framework Selection Guide

```
What does the agent do?
│
├─ Answers questions from a knowledge base
│  └─ Simple Q&A Agent (§2)
│
├─ Interacts with users conversationally
│  └─ COSTAR Framework (§1)
│
├─ Calls APIs, runs code, searches databases
│  └─ Tool-Using Agent (§3)
│
├─ Solves complex problems requiring analysis
│  └─ Multi-Step Reasoning Agent (§4)
│
├─ Operates in a specialized domain (legal, medical, etc.)
│  └─ Domain Expert Agent (§5)
│
├─ Part of a multi-agent pipeline
│  └─ Pipeline Agent (§6)
│
└─ Multiple of the above
   └─ Combine relevant sections from each framework
```

### Combining Frameworks

Real agents often need elements from multiple frameworks. Common combinations:

- **Tool-Using + Domain Expert**: An agent that uses APIs within a specialized domain
  (e.g., a financial agent that calls market data APIs)
- **COSTAR + Multi-Step Reasoning**: A customer-facing agent that needs to solve
  complex problems (e.g., a support agent debugging technical issues)
- **Pipeline + Tool-Using**: An agent in a chain that calls external services
  (e.g., a data enrichment agent that queries multiple APIs)

When combining, maintain a clear section hierarchy:
1. Identity & Mission (always first)
2. Domain Knowledge (if applicable)
3. Tools (if applicable)
4. Workflow / Reasoning Process
5. Output Format
6. Examples
7. Guardrails (always last)
