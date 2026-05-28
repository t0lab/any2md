---
name: prompt-engineering
description: >
  Generate, evaluate, and refine high-quality system prompts for LLM agents. This skill
  implements a meta-prompting pipeline: analyze task requirements → select prompt architecture
  → generate structured system prompt → self-critique and refine → output production-ready prompt.

  USE THIS SKILL whenever the user asks to: write a system prompt, create agent instructions,
  design a prompt for an LLM, improve/refine an existing prompt, create instructions for a chatbot
  or AI assistant, build a prompt template, optimize a prompt, or any task involving crafting
  instructions that will be fed to a language model as system-level guidance. Also trigger when
  the user says things like "make a prompt for", "write instructions for an agent", "system message",
  "prompt engineering", "meta-prompt", or wants to turn a task description into a well-structured
  LLM prompt. Even if the user just describes what an agent should do without explicitly asking
  for a "prompt", this skill should activate.
---

# Prompt Engineering Skill

## Overview

This skill generates production-grade system prompts for LLM agents. It synthesizes best
practices from OpenAI's meta-prompt strategy, Anthropic's prompt engineering guidelines,
the COSTAR framework, and academic meta-prompting research into a single, actionable pipeline.

## Pipeline

```
User Input (task description or existing prompt)
    │
    ▼
┌─────────────────────────────────────┐
│ Step 1: ANALYZE                     │  Classify task, identify constraints
│         (references/analysis.md)    │
├─────────────────────────────────────┤
│ Step 2: ARCHITECT                   │  Select prompt structure & framework
│         (references/frameworks.md)  │
├─────────────────────────────────────┤
│ Step 3: GENERATE                    │  Write the system prompt
│         (references/meta_prompt.md) │
├─────────────────────────────────────┤
│ Step 4: CRITIQUE & REFINE           │  Self-evaluate, fix gaps
│         (references/evaluation.md)  │
└─────────────────────────────────────┘
    │
    ▼
Production-ready system prompt
```

## Step 1: ANALYZE — Understand the Task

Before writing a single word, answer these questions:

1. **What is the agent's core mission?** — One sentence, verb-first.
2. **Who is the audience?** — End users, developers, internal team?
3. **What tools does the agent have?** — APIs, databases, search, code execution?
4. **What are the constraints?** — Safety, tone, length, format, domain boundaries?
5. **What does success look like?** — Concrete examples of ideal output.
6. **What must the agent NEVER do?** — Explicit guardrails.

Read `references/analysis.md` for the complete task analysis framework.

## Step 2: ARCHITECT — Choose Prompt Structure

Based on the analysis, select the appropriate architecture:

| Agent Type | Recommended Structure | When to Use |
|---|---|---|
| **Simple Q&A** | Identity + Instructions + Format | FAQ bots, lookup assistants |
| **Task Agent** | COSTAR (Context, Objective, Style, Tone, Audience, Response) | Customer service, writing |
| **Tool-Using Agent** | Identity + Capabilities + Tool Descriptions + Workflow + Guardrails | API agents, coding agents |
| **Multi-Step Reasoning** | Identity + Chain-of-Thought scaffold + Examples + Output Format | Analysis, research |
| **Domain Expert** | Identity + Domain Knowledge + Constraints + Few-Shot Examples | Legal, medical, financial |
| **Pipeline Agent** | Role + Input Schema + Processing Steps + Output Schema + Error Handling | Data processing, ETL |

Read `references/frameworks.md` for detailed templates of each structure.

## Step 3: GENERATE — Write the Prompt

Apply the meta-prompt template from `references/meta_prompt.md`. Key principles:

### The 10 Commandments of System Prompts

1. **Lead with identity** — First line defines who the agent IS.
2. **Be specific, not vague** — "Respond in 2-3 sentences" beats "Be concise".
3. **Reasoning before conclusions** — Tell the model to think, THEN answer.
4. **Show, don't just tell** — Include 1-3 examples with placeholders.
5. **Define the output format explicitly** — JSON, markdown, bullet points, length.
6. **Separate concerns with sections** — Use headers (##) or XML tags to organize.
7. **Include guardrails** — What the agent must NOT do is as important as what it should.
8. **Use constants, not variables** — Embed rubrics, guidelines, and rules directly.
9. **Order matters** — Place the most important instructions first and last (primacy/recency).
10. **Test with adversarial inputs** — Consider edge cases and misuse attempts.

### Prompt Structure Template

```
[One-line mission statement — who you are and what you do]

[Core instructions — 3-5 key behavioral rules]

## Context
[Domain knowledge, background information, data the agent needs]

## Instructions
[Step-by-step guidance for completing the task]

## Output Format
[Exact specification of response format, length, structure]

## Examples (optional)
[1-3 input/output pairs with [placeholders] for variable parts]

## Guardrails
[What to avoid, edge cases, safety constraints]
```

## Step 4: CRITIQUE & REFINE

After generating, evaluate against this checklist:

Read `references/evaluation.md` for the complete evaluation rubric. Quick check:

- [ ] **Clarity**: Could a new developer understand what this agent does in 10 seconds?
- [ ] **Completeness**: Are all edge cases covered?
- [ ] **Specificity**: Are instructions concrete (not "be helpful")?
- [ ] **No contradictions**: Do instructions conflict with each other?
- [ ] **Reasoning order**: Does the prompt ask for thinking BEFORE conclusions?
- [ ] **Output format**: Is the exact format specified?
- [ ] **Guardrails**: Are there explicit "never do X" instructions?
- [ ] **Examples**: Are there examples for complex outputs?
- [ ] **Length**: Is the prompt as short as possible without losing clarity?
- [ ] **Testability**: Can you verify if the agent follows these instructions?

## Quick-Start Decision Tree

```
What kind of prompt do you need?
│
├─ "Just improve my existing prompt"
│   → Read references/meta_prompt.md → Apply refinement meta-prompt
│
├─ "Create a prompt from a task description"
│   → Step 1 (Analyze) → Step 2 (Architect) → Step 3 (Generate) → Step 4 (Refine)
│
├─ "Create a prompt for a tool-using agent"
│   → Read references/frameworks.md § Tool-Using Agent → Generate with tool schema
│
├─ "Create a prompt for a DeepAgents/LangChain agent"
│   → Read references/frameworks.md § Pipeline Agent → Include tool definitions + state schema
│
└─ "I need a meta-prompt that generates other prompts"
    → Read references/meta_prompt.md → Use the Meta-Prompt Generator template
```

## File Reference

| File | Purpose | When to Read |
|---|---|---|
| `references/meta_prompt.md` | Core meta-prompt templates (OpenAI + Anthropic + custom) | Always — this is the generation engine |
| `references/frameworks.md` | 6 prompt architecture templates with examples | When choosing prompt structure |
| `references/analysis.md` | Task analysis framework, signal-word detection | When analyzing user requirements |
| `references/evaluation.md` | Self-critique rubric, common anti-patterns, refinement loop | After generating, before delivering |
| `references/techniques.md` | Advanced techniques (CoT, few-shot, XML tags, persona) | When optimizing for specific model families |
| `examples/` | Complete example prompts for common agent types | For reference and inspiration |
