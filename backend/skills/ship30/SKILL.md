---
name: ship30-essay
description: Turn grounded Lenny's Podcast evidence into a Ship 30 for 30-style essay (~1,250 words).
source: https://www.ship30for30.com/post/how-to-start-writing-online-the-ship-30-for-30-ultimate-guide
---

# Ship 30 for 30 essay skill

Principles extracted from the Ship 30 for 30 guide (Nicolas Cole & Dickie Bush) and encoded here so
the essay engine does not depend on a one-off prompt. This file is loaded at runtime by
`backend/agent/essay_skill.py`; edit it to change the writing rules.

## Principles
1. **Know WHO you write for and the outcome (SO THAT).** State the reader and the transformation in the hook.
2. **The headline is the North Star.** It promises where the essay goes; every section must deliver on it
   ("Clear over clever"). Add a one-line subtitle that sharpens the promise.
3. **Two-Year Test.** Write what you (or a peer two years behind) wished you had known two years ago.
4. **4A Framework** - cover all four angles, one `##` section each:
   - **Actionable** - concrete steps, frameworks, sequencing the reader can apply this week.
   - **Analytical** - metrics, benchmarks, data, cause-and-effect ("why this works").
   - **Aspirational** - the mindset shift and what winning looks like (story/vision).
   - **Anthropological** - why people and teams behave this way; incentives, friction, culture.
5. **Skimmable by design.** Readers skim: short paragraphs (1-3 sentences), descriptive subheads,
   bullets/numbered steps, selective **bold** on the key takeaway only.
6. **Specific, useful takeaway.** End with a single concrete next action.
7. **Ship, don't polish.** Prefer a clear first draft over ornament; no filler.

## Hard constraints for this product
- Length: ~1,250 words (accepted range 1,100-1,400). Note: classic Ship 30 *atomic* essays are 250-500 words;
  the assignment explicitly asks for a longer ~1,250-word piece, so the structure is scaled up, not changed.
- **Grounding:** every claim, number, name or quote must come from the supplied evidence chunks and carry a
  `[citation:CHUNK_ID]` token. Never invent statistics or quotes. If evidence is thin, say so instead of padding.
- Use quotation marks only for text that appears verbatim in the evidence.

## Required structure
```
# <Headline>
## <One-line subtitle>
<Hook: reader + problem + two-year-test framing, ~100 words>
## 1. Actionable: ...        (~35%)
## 2. Analytical: ...        (~25%)
## 3. Aspirational: ...      (~20%)
## 4. Anthropological: ...   (~20%)
## Your next step            (one concrete action)
```
