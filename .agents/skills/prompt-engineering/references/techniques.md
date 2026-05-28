# Advanced Prompting Techniques

## 1. Chain-of-Thought (CoT)

Force the model to show reasoning before answering.

**When to use**: Math, logic, analysis, classification, any task requiring reasoning.

**Implementation**:
```
Before answering, think through the problem step by step:
1. Identify the key elements of the question
2. Consider relevant factors
3. Work through the logic
4. State your conclusion
```

**Variant — Zero-Shot CoT**: Simply add "Let's think step by step" to the prompt.

**Variant — Structured CoT**: Provide a reasoning template:
```
## Analysis
- Key facts: [list relevant facts]
- Considerations: [list factors to weigh]
- Reasoning: [step-by-step logic]
## Conclusion
- Answer: [final answer]
- Confidence: [high/medium/low]
```

## 2. Few-Shot Examples

Provide input-output pairs to demonstrate desired behavior.

**When to use**: When output format is complex, tone is specific, or task is novel.

**Best practices**:
- 1-3 examples for simple tasks, 3-5 for complex tasks
- Use [placeholders] for variable parts
- Include at least one edge case example
- Order examples from simple to complex
- Make examples representative of real-world inputs

**Template**:
```
## Examples

**Input**: [realistic input]
**Output**: [ideal output demonstrating format, tone, and reasoning]

**Input**: [edge case input]
**Output**: [how to handle the edge case correctly]
```

## 3. XML Tags (Claude-Optimized)

Use XML tags to create clear semantic boundaries.

**When to use**: Complex prompts for Anthropic models; also works well with other models.

```
<context>
You are analyzing customer feedback for a SaaS product.
The product is a project management tool used by teams of 5-50 people.
</context>

<instructions>
Categorize each piece of feedback into one of: bug, feature_request,
praise, complaint, question.
Extract the key topic and sentiment score (-1 to 1).
</instructions>

<output_format>
{
  "category": "bug|feature_request|praise|complaint|question",
  "topic": "string",
  "sentiment": number,
  "summary": "1-sentence summary"
}
</output_format>

<examples>
<example>
<input>The kanban board keeps freezing when I have more than 50 cards</input>
<output>{"category": "bug", "topic": "kanban performance", "sentiment": -0.7, "summary": "User reports kanban board freezing with 50+ cards"}</output>
</example>
</examples>
```

## 4. Persona / Role Assignment

Anchor the model in a specific expertise.

**When to use**: Domain-specific tasks, when you want consistent expertise level.

**Levels of specificity**:
```
Weak:   "You are a helpful assistant."
Medium: "You are a data analyst."
Strong: "You are a senior data analyst at a Fortune 500 retail company
         with 10 years of experience in customer segmentation using
         RFM analysis. You communicate findings to non-technical
         stakeholders using business language."
```

## 5. Output Priming / Prefilling

Start the assistant's response to constrain the format.

**When to use**: When you need strict format adherence.

**Implementation** (for API calls):
```python
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "Analyze this data..."},
    {"role": "assistant", "content": '{"analysis": '}  # Prefill
]
```

## 6. Recursive Self-Improvement (RSIP)

Have the model critique and improve its own output.

**When to use**: High-stakes outputs where quality matters more than latency.

**Implementation in prompt**:
```
After generating your initial response:
1. Review your response critically
2. Identify any weaknesses, gaps, or errors
3. Generate an improved version addressing those issues
4. Output only the improved version
```

## 7. Constraint Prompting

Use explicit constraints to narrow the output space.

**Examples**:
```
- Respond in exactly 3 bullet points
- Use only words a 10-year-old would understand
- Do not use the words "innovative", "leverage", or "synergy"
- Every sentence must contain a number or statistic
- Your response must be valid JSON
- Maximum 100 words
```

## 8. Negative Prompting

Specify what NOT to do (use sparingly — positive instructions are stronger).

**When to use**: When the model has known failure modes you want to prevent.

```
## What NOT to do
- Do NOT apologize excessively or use phrases like "I'm sorry, but..."
- Do NOT provide medical/legal/financial advice
- Do NOT make up citations or references
- Do NOT repeat the user's question back to them
- Do NOT use corporate jargon or buzzwords
```

## 9. Meta-Cognitive Prompting

Ask the model to assess its own confidence and limitations.

```
After answering, rate your confidence on a scale of 1-5:
- 5: Certain — this is a well-established fact
- 4: High confidence — very likely correct
- 3: Moderate — reasonable answer but may have gaps
- 2: Low confidence — speculative, verify before acting
- 1: Uncertain — I'm guessing, seek expert advice

If your confidence is below 3, explicitly state what additional
information would raise your confidence.
```

## 10. Multi-Perspective Simulation

Have the model consider multiple viewpoints.

```
Before responding, consider this question from three perspectives:
1. **The optimist**: What's the best-case interpretation?
2. **The skeptic**: What could go wrong? What's being overlooked?
3. **The pragmatist**: What's the most actionable path forward?

Synthesize these perspectives into a balanced recommendation.
```

## Technique Selection Matrix

| Task Type | Primary Technique | Supporting Techniques |
|---|---|---|
| Classification | Few-Shot + Output Format | XML Tags |
| Analysis | Chain-of-Thought + Multi-Perspective | Meta-Cognitive |
| Content Generation | Persona + COSTAR | Constraint + Negative |
| Code Generation | Few-Shot + Chain-of-Thought | Output Priming |
| Data Extraction | XML Tags + Output Format | Few-Shot |
| Decision Making | Multi-Perspective + CoT | Meta-Cognitive |
| Agent Instructions | Persona + Framework Template | Constraint + Negative |
