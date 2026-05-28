# Prompt Evaluation & Refinement

## Evaluation Rubric

Score each dimension 1-5. A production prompt should score 4+ on all dimensions.

| Dimension | 1 (Poor) | 3 (Adequate) | 5 (Excellent) |
|---|---|---|---|
| **Clarity** | Ambiguous, multiple interpretations possible | Mostly clear, minor ambiguity | Crystal clear, one possible interpretation |
| **Completeness** | Missing critical instructions | Covers main cases, some gaps | All cases covered including edge cases |
| **Specificity** | Vague ("be helpful") | Somewhat specific | Precise ("respond in 2-3 sentences using...") |
| **Structure** | Wall of text | Some organization | Clean sections, logical flow |
| **Examples** | No examples for complex tasks | Examples present but generic | Realistic examples with placeholders |
| **Guardrails** | No safety/boundary instructions | Basic "don't do X" | Comprehensive guardrails with fallback behaviors |
| **Output Format** | Format unspecified | General format mentioned | Exact format, length, schema specified |
| **Testability** | Cannot verify compliance | Some instructions verifiable | Every instruction can be tested |

## Common Anti-Patterns

### 1. The Vague Opener
**Bad**: "You are a helpful assistant."
**Good**: "You are a financial data analyst that transforms raw quarterly earnings data into executive-ready summaries."

### 2. The Kitchen Sink
**Bad**: A 3000-word prompt covering every possible scenario.
**Good**: Core instructions (80% of cases) in the prompt, with clear escalation for the remaining 20%.

### 3. Contradictory Instructions
**Bad**: "Be concise." ... "Always provide comprehensive analysis with full details."
**Good**: "Provide a 2-3 sentence summary, followed by detailed analysis only if the user asks for more."

### 4. Conclusions Before Reasoning
**Bad**: "Classify the sentiment, then explain why."
**Good**: "First, identify key emotional indicators in the text. Then, based on these indicators, classify the sentiment."

### 5. Missing Output Format
**Bad**: "Analyze the data and give me insights."
**Good**: "Analyze the data and return a JSON object with: { summary: string, key_metrics: [{ name, value, trend }], recommendations: string[] }"

### 6. Implicit Knowledge Assumption
**Bad**: "Follow our company's standard format."
**Good**: [Include the actual format template in the prompt]

### 7. No Failure Mode
**Bad**: [No mention of what happens when the agent can't help]
**Good**: "If you cannot answer the question, say 'I don't have enough information to answer that. Here's what I would need: [list missing info]'"

### 8. Over-Relying on "Don't"
**Bad**: "Don't be rude. Don't give wrong information. Don't be too verbose."
**Good**: "Maintain a professional, warm tone. Verify claims against your knowledge base before stating them. Keep responses under 200 words unless the user requests more detail."

## Refinement Loop

After initial generation, run this 3-pass refinement:

### Pass 1: Adversarial Testing
Ask yourself: "If I were trying to break this agent, what would I try?"
- Ambiguous inputs
- Out-of-scope requests
- Contradictory instructions
- Prompt injection attempts
- Edge cases (empty input, very long input, different languages)

### Pass 2: Compression
For each sentence in the prompt, ask: "If I remove this, does the agent's behavior change?"
- If NO → remove it (it's noise)
- If YES → keep it (it's signal)

### Pass 3: Clarity Check
Read each instruction and ask: "Could a literal-minded junior developer misinterpret this?"
- If YES → rewrite to be unambiguous
- If NO → it's clear enough

## Prompt Length Guidelines

| Agent Complexity | Recommended Length | Key Sections |
|---|---|---|
| Simple Q&A | 200-500 tokens | Identity + Instructions + Format |
| Standard Agent | 500-1500 tokens | Full framework template |
| Complex Agent | 1500-3000 tokens | Full framework + examples + guardrails |
| Pipeline Agent | 1000-2000 tokens | Schema-heavy, workflow-focused |

Longer is NOT better. Every token in the prompt competes with the context window
available for the actual task. Optimize for signal density.
