---
name: searcharvester-deep-research
description: >
  End-to-end deep-research methodology with PARALLEL sub-agents. Given any
  research question, decompose it into sub-questions, dispatch a fresh
  delegate_task per sub-question (each sub-agent runs its own search +
  extract loop), then synthesise all returns into a cited markdown report
  saved to /workspace/report.md. Use when the user asks for "research",
  "deep research", "report with sources", comparisons with citations, or
  any answer that must be grounded in 15+ web sources.
version: 2.0.0
author: Searcharvester
license: MIT
metadata:
  hermes:
    tags: [research, deep-research, delegate_task, parallel, subagents, citations]
    category: research
    related_skills:
      - searcharvester-search
      - searcharvester-extract
      - subagent-driven-development
      - writing-plans
      - plan
---

# Searcharvester Deep Research

Turn an open-ended question into a **markdown report grounded in 15+ web
sources** via a parallel-subagent workflow. Save to `/workspace/report.md`.

## Role

You are the **lead researcher**. Your job is to:
1. Decompose the question.
2. Dispatch `delegate_task` sub-agents in parallel, one per sub-question.
3. Collect their findings.
4. Write the final synthesis.

You do NOT personally run `searcharvester-search` / `searcharvester-extract`.
The sub-agents do that work in parallel — you only orchestrate.

## When to use

Use this skill for any task that needs **web evidence with citations**:

- "Research X" / "deep research on X" / "analyse X"
- "Compare A vs B with sources"
- "What's known publicly about X"
- "Find contacts / profiles / mentions of [named person or company]"
- "What's the latest on X" (needs current info)

Do **not** use this skill for:

- Simple factual questions you can answer from parametric knowledge.
- Code writing / debugging.

## Core principle

**Evidence before prose.** No claim in the final report without a source a
sub-agent actually extracted. If a sub-agent returned "no source found"
for a sub-question, that's a valid finding — include it in the report as
"unknown / no public source found".

## Procedure

### Phase 1 — Decompose (you, lead)

Read the question. Write a short plan **to `/workspace/plan.md`** using the
`terminal` tool (`cat > /workspace/plan.md << 'EOF' ... EOF`). The plan has:

1. **Intent** — one sentence: what does the user want to learn?
2. **Sub-questions** — **3–6 independently researchable** sub-questions.
   Each must be tight enough that a fresh sub-agent with zero context can
   research it and return a short structured answer.
3. **Out of scope** — things you will NOT cover.

Example plan for *"Find public contacts of [name]"*:

```markdown
## Intent
Identify all publicly available professional contact points for X.

## Sub-questions
1. Professional profile / employer / job title (company website, Forbes,
   press mentions).
2. Social media presence (LinkedIn, GitHub, X/Twitter, Telegram).
3. Academic or conference presence (arXiv, conference author pages).
4. Personal website / blog / newsletter if any.
5. Aggregator / directory listings (RocketReach, ContactOut, company
   directories).

## Out of scope
- Home address, personal phone numbers, leaked data.
- Inferred emails from patterns — only list what sources actually show.
```

### Phase 2 — Dispatch sub-agents in parallel (you, lead)

For **each** sub-question, dispatch a fresh `delegate_task` sub-agent.
Key points:

- **Fresh context per sub-agent.** Each sub-agent gets only its own
  sub-question, not the whole plan. Don't make them re-plan.
- **Give them OUR tools**: pass skills `searcharvester-search` and
  `searcharvester-extract` in the `skills` argument.
- **Enable terminal toolset** so the sub-agent can call our python scripts.
- **Ask for structured output**: each sub-agent must return JSON or short
  markdown in a prescribed shape (see template below) so you can merge
  them mechanically.

Template for each `delegate_task` call:

```python
delegate_task(
    goal="Research sub-question N for parent task",
    context="""
    SUB-QUESTION:
    <paste the sub-question verbatim>

    CONTEXT FROM PARENT:
    The user asked: "<original user query>"

    YOUR TOOLS:
    - searcharvester-search  — web search (SearXNG, 100+ engines)
    - searcharvester-extract — URL → clean markdown (trafilatura)
    - terminal              — to invoke the scripts above

    METHOD:
    1. Run 2–4 searches with varied phrasings (different angles, English
       and the question's language if non-English).
    2. Pick 3–6 most authoritative URLs from the results.
    3. Extract each picked URL (searcharvester-extract --size m).
    4. If an extract fails (422/502), immediately pick another URL.
    5. Aim for 4–6 successful extracts for this sub-question.

    RETURN FORMAT — reply with a markdown block exactly in this shape:
    ### Sub-question N findings
    - **Claim**: <one-sentence factual claim>
      **Quote**: "<relevant verbatim quote from the source>"
      **URL**: <url>
    - **Claim**: ...
      **Quote**: ...
      **URL**: ...
    (4–8 bullets)

    Do NOT write a full report. Do NOT add sections outside the template.
    Do NOT call searcharvester-deep-research recursively.
    """,
    skills=["searcharvester-search", "searcharvester-extract"],
    toolsets=["terminal"],
)
```

Dispatch **all** sub-agents before doing anything else. Hermes runs
delegate_task calls concurrently when you queue them without waiting.

### Phase 3 — Synthesise (you, lead)

Once all sub-agents return:

1. **Collect their markdown blocks** from the delegate_task results.
2. **Build a unified reference list** — dedupe URLs, assign `[1]`, `[2]`,
   ... in order of first appearance.
3. **Write `/workspace/report.md`** with this structure:

   ```markdown
   # <Title — reflects the actual question, not generic>

   ## TL;DR
   <2–4 sentence summary a busy reader can take away>

   ## <Sub-topic 1>
   <Claims with inline `[n]` citations pointing to References>

   ## <Sub-topic 2>
   ...

   ## Caveats and open questions
   <Bullets — what wasn't found, sub-agents that came back empty>

   ## References
   [1] <short label> — <URL>
   [2] <short label> — <URL>
   ```

4. Hard rules:
   - Every factual claim has an inline `[n]` citation.
   - Same URL = same number.
   - Use tables when comparing 3+ items.
   - No marketing adjectives ("powerful", "robust", ...) unless quoted.
   - Numbers get units and dates when available.
   - Match the user's language.

### Phase 4 — Deliver (you, lead)

Verify before closing:
- [ ] `/workspace/report.md` exists and is >500 bytes.
- [ ] References list has **≥15 unique URLs** (target 20–30 across all
      sub-agents' returns).
- [ ] Every non-TL;DR, non-References section has at least one `[n]`.
- [ ] TL;DR is standalone (no citations, no "see below").

Then print as the **very last line**:
```
REPORT_SAVED: /workspace/report.md
```

## Pitfalls

- **Doing research yourself.** You are the lead. If you're calling
  `searcharvester-search` directly instead of via `delegate_task`, stop
  and go to Phase 2.
- **Too few sub-agents.** Fewer than 3 = you're not decomposing enough.
  Too broad a sub-question → sub-agent returns thin results.
- **Too many sub-agents.** More than 7 = decomposition too fine-grained;
  merge overlapping sub-questions.
- **Sub-agents without skills.** If you forget to pass
  `skills=["searcharvester-search", "searcharvester-extract"]` the
  sub-agent won't have tools and will return an error or hallucinate.
- **Free-form sub-agent output.** Always require the "Sub-question N
  findings" template. Free text is painful to merge.
- **Nested delegation.** Sub-agents must NOT call `searcharvester-deep-
  research` themselves. That's recursion and burns tokens for nothing.
- **Publishing the plan.** `/workspace/plan.md` is for the sub-agents'
  context, not the final output. Only `/workspace/report.md` matters to
  the user.
