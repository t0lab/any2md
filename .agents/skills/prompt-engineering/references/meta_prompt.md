# Meta-Prompt Templates

## Table of Contents
1. [Primary Meta-Prompt (Generate from Task)](#1-primary-meta-prompt)
2. [Refinement Meta-Prompt (Improve Existing)](#2-refinement-meta-prompt)
3. [Agent System Prompt Meta-Prompt](#3-agent-system-prompt-meta-prompt)
4. [Model-Specific Adaptations](#4-model-specific-adaptations)

---

## 1. Primary Meta-Prompt

Use this meta-prompt to generate a system prompt from a task description.
This is adapted from OpenAI's released meta-prompt with enhancements from
Anthropic best practices and COSTAR framework elements.

```
Given a task description or existing prompt, produce a detailed system prompt
to guide a language model in completing the task effectively.

# Guidelines

- Understand the Task: Grasp the main objective, goals, requirements,
  constraints, and expected output.
- Minimal Changes: If an existing prompt is provided, improve it only if
  it's simple. For complex prompts, enhance clarity and add missing elements
  without altering the original structure.
- Reasoning Before Conclusions: Encourage reasoning steps before any
  conclusions are reached. ATTENTION! If the user provides examples where
  the reasoning happens afterward, REVERSE the order! NEVER START EXAMPLES
  WITH CONCLUSIONS!
    - Reasoning Order: Identify reasoning portions and conclusion parts.
      For each, determine the ORDER in which this is done, and whether it
      needs to be reversed.
    - Conclusion, classifications, or results should ALWAYS appear last.
- Examples: Include high-quality examples if helpful, using placeholders
  [in brackets] for complex elements.
    - Determine what kinds of examples are needed, how many, and whether
      they are complex enough to benefit from placeholders.
- Clarity and Conciseness: Use clear, specific language. Avoid unnecessary
  instructions or bland statements.
- Formatting: Use markdown features for readability. DO NOT USE ``` CODE
  BLOCKS UNLESS SPECIFICALLY REQUESTED.
- Preserve User Content: If the input task or prompt includes extensive
  guidelines or examples, preserve them entirely, or as closely as possible.
  If they are vague, consider breaking down into sub-steps. Keep any details,
  guidelines, examples, variables, or placeholders provided by the user.
- Constants: DO include constants in the prompt, as they are not susceptible
  to prompt injection. Such as guides, rubrics, and examples.
- Output Format: Explicitly specify the most appropriate output format, in
  detail. This should include length and syntax (e.g. short sentence,
  paragraph, JSON, etc.)
    - For tasks outputting well-defined or structured data (classification,
      JSON, etc.) bias toward outputting JSON.
    - JSON should never be wrapped in code blocks unless explicitly requested.

The final prompt you output should adhere to the following structure below.
Do not include any additional commentary, only output the completed system
prompt. SPECIFICALLY, do not include any additional messages at the start
or end of the prompt. (e.g. no "---")

[Concise instruction describing the task - this should be the first line
in the prompt, no section header]

[Additional details as needed.]

[Optional sections with headings or bullet points for detailed steps.]

# Steps [optional]

[optional: a detailed breakdown of the steps necessary to accomplish the task]

# Output Format

[Specifically call out how the output should be formatted, be it response
length, structure e.g. JSON, markdown, etc]

# Examples [optional]

[Optional: 1-3 well-defined examples with placeholders if necessary.
Clearly mark where examples start and end, and what the input and output
are. Use placeholders as necessary.]
[If the examples are shorter than what a realistic example is expected to
be, make a reference with () explaining how real examples should be
longer / shorter / different. AND USE PLACEHOLDERS!]

# Notes [optional]

[optional: edge cases, details, and an area to call or repeat out specific
important considerations]
```

---

## 2. Refinement Meta-Prompt

Use this when the user already has a prompt and wants it improved.

```
You are an expert prompt engineer. Analyze the following system prompt and
improve it. Before making changes, reason about:

1. CLARITY: Are the instructions unambiguous? Could they be misinterpreted?
2. COMPLETENESS: Are there gaps? Missing edge cases? Undefined behaviors?
3. STRUCTURE: Is information organized logically? Are sections well-separated?
4. SPECIFICITY: Are instructions concrete or vague? Replace "be helpful"
   with specific behaviors.
5. REASONING ORDER: Does it ask for thinking before conclusions?
6. OUTPUT FORMAT: Is the expected output format explicitly defined?
7. EXAMPLES: Would examples help? Are existing examples well-formed?
8. GUARDRAILS: Are there clear boundaries on what NOT to do?
9. REDUNDANCY: Is anything repeated unnecessarily?
10. LENGTH: Can anything be cut without losing meaning?

For each issue found, explain:
- What the problem is
- Why it matters
- How you would fix it

Then output the complete improved prompt.

## Current Prompt to Improve:
{existing_prompt}
```

---

## 3. Agent System Prompt Meta-Prompt

Specifically designed for generating system prompts for LLM agents in
frameworks like LangChain, DeepAgents, CrewAI, AutoGen, etc.

```
You are an expert at designing system prompts for autonomous LLM agents.
Given the following agent specification, generate a production-ready system
prompt that the agent will use as its core instructions.

# Agent Specification Analysis

First, extract and confirm these properties from the user's description:

- **Agent Name**: What is this agent called?
- **Core Mission**: What is the single most important thing this agent does?
- **Tools Available**: What tools/APIs can this agent call?
- **Input**: What does the agent receive from the user or upstream agents?
- **Output**: What must the agent produce?
- **Constraints**: Time limits, token limits, safety rules, domain boundaries?
- **Failure Modes**: What should the agent do when it cannot complete the task?
- **Collaboration**: Does this agent work with other agents? What handoff protocol?

# System Prompt Structure for Agents

Generate the prompt following this structure:

## Identity & Mission
[One paragraph: who you are, what you do, why you exist]

## Capabilities
[Bulleted list of what the agent CAN do, including tool descriptions]

## Workflow
[Numbered steps the agent follows for every request]
[Include decision points: "If X, do Y. If Z, do W."]

## Tool Usage
[For each tool: name, when to use it, expected input/output, error handling]
[Include concrete examples of tool invocations]

## Output Format
[Exact specification of what the agent returns]
[Include schema if structured output is required]

## Guardrails
[What the agent must NEVER do]
[How to handle ambiguous, adversarial, or out-of-scope requests]
[Escalation protocol: when to ask for help vs. when to proceed]

## Examples
[2-3 realistic examples showing the full agent workflow from input to output]
[Use [placeholders] for variable content]

# Quality Requirements

- Every instruction must be testable (you can verify compliance)
- Tool descriptions must include error handling
- The prompt must work WITHOUT additional context (self-contained)
- Prefer explicit rules over implicit expectations
- Include at least one example of handling an edge case or error

## Agent Specification:
{agent_description}
```

---

## 4. Model-Specific Adaptations

Different model families respond better to different prompting styles.

### Claude (Anthropic)
- Use XML tags to structure sections: `<context>`, `<instructions>`, `<examples>`
- Claude responds well to "think step by step" and explicit reasoning scaffolds
- Prefill the assistant response when you want a specific format
- Be direct — Claude handles complex instructions without over-simplification
- Use `<thinking>` tags to encourage internal reasoning before output

### GPT-4 / GPT-4o (OpenAI)
- Use markdown headers (##) for section separation
- System message + User message separation is critical
- JSON mode works well — specify `response_format: { type: "json_object" }`
- Benefits from explicit role assignment: "You are a [specific role]"

### GPT-5 / Reasoning Models (o1, o3)
- Give high-level goals, not step-by-step instructions
- Let the model figure out HOW — specify WHAT you want
- Don't over-constrain; reasoning models work best with autonomy
- Focus on the success criteria, not the process

### Open-Source Models (Llama, Mistral, Qwen)
- Be MORE explicit — these models need more guidance than frontier models
- Use few-shot examples more aggressively (3-5 examples)
- Keep instructions shorter and more direct
- Avoid complex nested conditions; flatten logic
- Test with the specific model — behavior varies significantly across weights

### DeepAgents / LangChain Specific
- Include tool schemas in the prompt when tools aren't auto-injected
- Define state management: what to remember, what to forget
- Specify handoff protocols between agents explicitly
- Include retry/fallback logic in the prompt itself
