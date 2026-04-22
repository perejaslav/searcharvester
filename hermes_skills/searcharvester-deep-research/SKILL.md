---
name: searcharvester-deep-research
description: >
  End-to-end methodology for writing research reports from web sources. Given
  any research question, decompose into sub-queries, gather evidence via
  searcharvester-search and searcharvester-extract, synthesise a cited markdown
  report and save it to /workspace/report.md. Use when the user asks for a
  "research report", "deep research", "analysis with sources", or any answer
  that must cite primary web sources.
version: 1.0.0
author: Searcharvester
license: MIT
metadata:
  hermes:
    tags: [research, deep-research, synthesis, citations, markdown, report]
    category: research
    related_skills:
      - searcharvester-search
      - searcharvester-extract
      - plan
      - writing-plans
---

# Searcharvester Deep Research

## What this skill does

Turn an open-ended research question into a **self-contained markdown report**,
grounded in **real web sources you read end-to-end**, with citations in
`[1]`, `[2]` style and a reference list at the bottom. The output is written
to `/workspace/report.md` so downstream tooling can pick it up.

## When to use

Use this skill whenever the user asks for:

- "Write a research report on X"
- "Deep research on X with sources"
- "Compare A vs B, cite your sources"
- "What's the latest on X" (expects current info from the web)
- "Analyse X" (expects cited analysis, not vibes)

Do **not** use this skill for:

- Pure "what is X" questions you can answer from parametric knowledge — just reply.
- Code writing / debugging — use `plan` + `subagent-driven-development`.
- Academic paper drafting — use `research-paper-writing`.

## Core principle

**Evidence before prose.** You are not allowed to write a claim in the report
that is not backed by a concrete source you have actually read. If you can't
find a source, say "no source found" — do not hallucinate.

## Depth budget

**Aim for 20–30 distinct sources actually extracted**, not just found in search
results. Depth beats breadth:

- **Minimum:** 15 successful `searcharvester-extract` calls across 4+ domains
  before you're allowed to write the report.
- **Target:** 20–30 successful extracts covering 6+ domains, 3–7 sub-questions.
- **Only stop earlier** if the question is genuinely narrow (e.g. "what is X
  in one sentence") — and even then, at least 3 extracts for cross-reference.

Plan search queries to maximise coverage: vary phrasings, include the target's
own URLs (personal site, GitHub, company page), try English and the user's
language, try `site:wikipedia.org`, `site:github.com`, news / press queries.
Each sub-question deserves **multiple** search calls with different angles.

## Procedure

Follow the five phases in order. Do not skip phases. Do not mix them.

### Phase 1 — Decompose

Read the question. Write a short plan **to `/workspace/plan.md`**. The plan
must contain:

1. **Intent**: one sentence — what does the user actually want to learn?
2. **Sub-questions**: 3–7 concrete, independently researchable sub-questions.
   Prefer questions whose answers are facts (dates, numbers, names,
   comparisons) over vague ones.
3. **Out of scope**: things you will NOT cover (keeps you focused).

Example plan for "compare vLLM vs SGLang for self-hosted LLM serving":

```markdown
# Plan: vLLM vs SGLang

## Intent
Help the user choose between vLLM and SGLang for a self-hosted inference
stack on NVIDIA H100, prioritising throughput and ease of deployment.

## Sub-questions
1. What is the latest stable release of each (version, date)?
2. What are the headline performance benchmarks (tokens/s) on H100?
3. How does each handle continuous batching and KV cache?
4. What model families does each support out of the box?
5. What's the deployment story (Docker, Kubernetes, binary)?
6. Which has better OpenAI-compatible API coverage (tool calls, streaming)?

## Out of scope
- TensorRT-LLM, Triton (user asked specifically about vLLM vs SGLang).
- Edge / CPU inference.
```

Write the plan, then move to phase 2. Don't skip to search before the plan is
on disk.

### Phase 2 — Gather

For each sub-question:

1. **Search**: call `searcharvester-search` with a focused query. Start with
   `--max-results 5`. If results look weak, retry with different engines
   (`--engines duckduckgo,brave`) or categories (`--categories news` for
   recency-sensitive questions).
2. **Pick 3–5 candidate sources** per sub-question (not 1–2): aim for
   primary sources (official docs, github repo, author's blog, benchmark
   authors) and corroborating secondary sources. More sources = stronger
   report. Don't stop at the first matching result.
3. **Extract**: call `searcharvester-extract --size m` on each chosen URL.
   - If the answer is in the first 10 000 chars — done.
   - If the document is long and relevant — use `--size f` and paginate via
     `--id --page`.
   - If extraction fails (422/502) — **immediately pick another URL** from
     your search results and extract it. Failed extracts don't count toward
     the depth budget.
4. **Note** what you learned, with the URL, **into `/workspace/notes.md`**:

```markdown
## Sub-question 2: headline throughput on H100

Source: https://blog.vllm.ai/...
- claim: vLLM 0.8 reaches 43 tok/s for Llama-3 70B AWQ on H100
- quote: "...43.1 tokens/second at batch size 64..."
- caveat: batch-dependent; smaller batches are ~20 tok/s

Source: https://lmsys.org/blog/sglang-benchmark
- claim: SGLang 0.4 reaches 52 tok/s on same hardware/model
- quote: "...52.4 tok/s sustained at batch 64..."
```

Don't summarise yet. Just collect evidence with quotes + URLs.

### Phase 3 — Gap check

After gathering for all sub-questions, **re-read `/workspace/notes.md`** and
ask:

- Is any sub-question unanswered?
- Are any claims from one source directly contradicted by another? If so,
  flag it — you need both sides in the report.
- Are any "facts" still vague (no number, no date)? Try one more targeted
  search to nail them down.

If gaps found: go back to Phase 2 for just those questions. Do **not** move
to synthesis with known gaps.

### Phase 4 — Synthesise

Now write `/workspace/report.md`. Structure:

```markdown
# <Title — reflects the actual question, not generic>

## TL;DR
<2–4 sentence summary a busy reader can take away>

## <Sub-topic 1 title>
<Claim with inline citation [1].> <Next claim [2].>
<A comparison table if appropriate>

## <Sub-topic 2 title>
...

## Caveats and open questions
<Bullets — what we couldn't pin down, where sources disagreed>

## References
[1] <Short label> — <URL>
[2] <Short label> — <URL>
```

Hard rules for the report:

- **Every factual claim has a `[n]` inline citation** pointing to the
  References list.
- The same URL = same reference number (don't cite the same source as [1]
  and then [4]).
- Use **tables** when comparing things. Plain prose for two items is fine;
  three or more → table.
- **No marketing language**: "powerful", "robust", "industry-leading" are
  banned unless directly quoted from a source.
- Numbers get units and dates (`43 tok/s on H100, Llama-3 70B AWQ, batch 64,
  benchmarked 2025-06-12`).
- Length: match the question. A comparison gets ~300–800 words. A deep
  technical dive gets 1000–2000.
- Write in the same language as the user's question. Don't switch to English
  unless the user did.

### Phase 5 — Verify and deliver

Before ending:

1. Re-read your own report. For each citation `[n]`, can you point at the
   exact quote or claim in `/workspace/notes.md` that it's based on? If
   not — remove the claim or fix the citation.
2. Delete `/workspace/plan.md` and `/workspace/notes.md` if they contain
   anything the user shouldn't see. Or leave them — they're useful artifacts
   and the orchestrator can pick them up.
3. Print a one-line confirmation at the end of your turn:
   `REPORT_SAVED: /workspace/report.md`.

The orchestrator looks for exactly that line as a machine-readable success
signal.

## Pitfalls

- **Tool flailing**: calling search 10 times with minor query variations
  instead of reading the results you already have. Stop searching once you
  have 2 good sources per sub-question.
- **Extracting everything**: `extract --size f` on a 100k-char page is a
  waste. Use `--size m` by default, only paginate when the specific answer
  you need isn't in the first 10k.
- **Plagiarism of snippets**: search results return short snippets. Don't
  paste them verbatim as your findings — extract the real page and quote
  from it.
- **Invisible tool output**: if an extract call returns no useful content
  (all nav/boilerplate), don't cite it. Pick another URL.
- **Going off-scope**: don't research things the plan marked out-of-scope,
  even if they're interesting.
- **Citing search snippets as sources**: the `url` + `title` from
  `/search` is a pointer, not evidence. Always extract before citing.

## Verification checklist

Before printing `REPORT_SAVED:`, verify:

- [ ] `/workspace/report.md` exists and is >500 bytes
- [ ] Every `## section` other than TL;DR and References has at least one
      `[n]` citation
- [ ] References list has ≥2 unique URLs
- [ ] TL;DR is present and standalone (no citations, no "...see below")
- [ ] No claim uses "powerful/robust/industry-leading" without a quoted source
- [ ] Language matches the user's question language

If any checkbox is missed — fix it before closing the turn.
