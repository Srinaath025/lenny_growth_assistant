# UI/UX Design Specification
## The Lenny Growth Assistant
**Document Version:** 1.1.0  
**Target Completion Date:** 12 October 2026  
**Status:** Approved for Design & Planning (Read-Only Stage)  
**Execution Strategy:** Local-First Design (Ollama Default with Disabled Cloud State)  
**Author:** Forward Deployed Engineering Team  

---

## 1. Design System & Aesthetic Foundation (Impeccable Style)

The user interface of *The Lenny Growth Assistant* adheres strictly to the design principles established by **Impeccable** (`impeccable.style`):
1. **Zero "AI Slop":** Avoids generic defaults (overused gradients, unstyled cards, low-contrast text).
2. **Intentional Typography:** Editorial typography pairing an elegant serif for long-form essays (`Newsreader`, Georgia) with a clean grotesque sans-serif (`Inter`) for interactive controls and citations.
3. **Tinted Obsidian Palette:** Replaces flat black with warm obsidian tones (`#0C0D0E`, `#141618`) accented by warm amber (`#F59E0B`), verified blue (`#38BDF8`), and guardrail rose (`#F43F5E`).
4. **Transparent System Telemetry:** Explicit, visible state indicators for local daemon health, active model, token streaming, and disabled cloud configurations.

### 1.1 Color Palette & Design Tokens

```css
:root {
  /* Warm Obsidian Dark Mode */
  --bg-primary: #0C0D0E;       /* Deep warm obsidian canvas */
  --bg-secondary: #141618;     /* Surface layer for cards and sidebars */
  --bg-tertiary: #1C1F22;      /* Interactive hover and elevated containers */
  --border-subtle: #25292E;    /* Subtle perimeter dividers */
  --border-prominent: #3B4048; /* Focused or active border elements */
  
  /* Text & Foreground */
  --text-primary: #F0F2F5;     /* High contrast primary text */
  --text-secondary: #9DA3AE;   /* Secondary descriptive text */
  --text-muted: #666D79;       /* Timestamps, metadata, footnotes */
  --text-disabled: #474E59;    /* Disabled controls and unconfigured options */
  
  /* Status & Accent Colors */
  --accent-amber: #F59E0B;     /* Brand accent: Growth Warmth */
  --accent-blue: #38BDF8;      /* Verifiable citation highlight */
  --accent-emerald: #10B981;   /* Local Ollama active / Healthy status */
  --accent-rose: #F43F5E;      /* Abstention banner / Error state */
  
  /* Typography */
  --font-serif: 'Newsreader', Georgia, serif;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  
  /* Dimensions */
  --sidebar-width: 280px;
  --artifact-drawer-width: 520px;
  --header-height: 56px;
}
```

---

## 2. Core Layout & Model Selector Design

```
+---------------------------------------------------------------------------------------------------------+
|                                              APPLICATION HEADER                                         |
|  [Logo] Lenny Growth Assistant   |  Session: "Elena Verna PLG Loops"     |  [Model Badge]  |  [Drawer Toggle]  |
+-------------------+----------------------------------------------------+--------------------------------+
|  SESSION SIDEBAR  |              CHAT STAGE (CENTER FEED)              |     ARTIFACT VIEWER (DRAWER)   |
|                   |                                                    |                                |
|  [+ New Session]  |  [User Message Bubble]                             |  +--------------------------+  |
|                   |  "Explain retention curves from Brian Balfour"     |  | Tab: Preview | Code      |  |
|  History:         |                                                    |  +--------------------------+  |
|  - Brian Balfour  |  [Assistant Synthesis Stream]                      |  | Ship 30 for 30 Essay:    |  |
|    Retention Loop |  "According to Brian Balfour in Episode #42,       |  | "Why Retention Is The    |  |
|  - Pricing Models |  retention is not a linear funnel..."              |  |  Only Growth Metric..."  |  |
|  - Shreyas Doshi  |                                                    |  |                          |  |
|    Product Sense  |  +----------------------------------------------+  |  | [1,248 words]           |  |
|                   |  | CITATION CARD #1                             |  |  |                          |  |
|  ---------------- |  | Guest: Brian Balfour | Ep #42                |  |  | [Sandboxed <iframe>]    |  |
|  Model Selector:  |  | Quote: "Retention drives acquisition loops..."|  |  |                          |  |
|  (•) Local Ollama |  | [Play on YouTube: 14:32]                     |  |  |                          |  |
|      (llama3.2:3b)|  +----------------------------------------------+  |  |                          |  |
|  (X) Cloud Claude |                                                    |  | [Copy]  [Download]       |  |
|      [LOCKED]     |  [Input Box: Ask Lenny Growth Assistant...] [Send] |  +--------------------------+  |
+-------------------+----------------------------------------------------+--------------------------------+
```

---

## 3. Model Selector & Telemetry States

### 3.1 Model Selector Control (Sidebar & Header)
The Model Selector gives the user immediate insight into active compute resources:

#### Option 1: Local Ollama (`llama3.2:3b`) — [DEFAULT & ACTIVE]
* **Visual State:** Radio option selected with a pulsing green status indicator dot.
* **Label:** `Local Ollama (llama3.2:3b)`
* **Telemetry Badge:** `🟢 Ollama 0.40.2 Ready` (queried from `GET /api/health`).

#### Option 2: Cloud Claude (model set by ANTHROPIC_MODEL) — [DISABLED WHEN KEY ABSENT]
* **Visual State (No Key Configured):**
  - Radio button is visibly disabled / greyed out with a subtle padlock icon (`🔒`).
  - **Label:** `Cloud Claude (model set by ANTHROPIC_MODEL) (Disabled)`
  - **Hover Tooltip / Inline Note:**  
    `"Cloud inference is currently disabled because ANTHROPIC_API_KEY is not set in the backend environment. Local Ollama mode is fully active for all queries."`
  - Clicking does not trigger any error or crash; the UI highlights the explanatory tooltip.
* **Visual State (Key Configured):**
  - Fully interactive radio toggle allowing instantaneous switching to Anthropic Claude.

---

## 4. Detailed Component Specifications

### 4.1 Session History Sidebar (Left Pane)
* **`+ New Session` Action:** Prominent button at top of sidebar with hotkey shortcut (`Ctrl + N`).
* **Chronological Session List:** Groups conversations by date (Today, Yesterday, Previous 7 Days).
* **Inline Actions:** Hover reveals `Rename` and `Delete` (trash icon) controls.

### 4.2 Chat Stream & Source Citation Cards
* **Streaming Message Feed:** Assistant responses stream progressively with a subtle blinking amber cursor.
* **Citation Card Anatomy:**
  - **Header:** Guest avatar, Guest Name (`Brian Balfour`), Episode Title (`Building Growth Loops`).
  - **Verbatim Excerpt:** Exact transcript quote rendered in an editorial italic quote block.
  - **Timestamp Action Pill:** Clickable YouTube icon button:  
    `▶ Watch on YouTube (18:45)`  
    Deep-links directly to `https://www.youtube.com/watch?v=VIDEO_ID&t=1125s` in a new tab.

### 4.3 Evidence-Based Abstention Visual Banner
When the system identifies that a question cannot be grounded in transcripts:
* **Visual Treatment:** Rose-tinted guardrail card (`rgba(244, 63, 94, 0.08)` background, `--accent-rose` border).
* **Heading:** `Topic Not Discussed in Transcripts`
* **Body:**  
  *"Based on our search across all ingested Lenny's Podcast episodes, neither Lenny nor his guests discussed this topic. To prevent ungrounded hallucinations, the assistant declines to answer."*
* **Zero Citations:** Citation section is omitted.

### 4.4 Ship 30 for 30 Essay Generation Flow
* **Quick-Prompt Chip:** Prominently positioned above the chat input:  
  `✍️ Draft Ship 30 for 30 Essay on [Topic]`
* **Generation Stepper:**
  1. `[✓] Identifying relevant guests and episodes...`
  2. `[✓] Extracting 4A insights (Actionable, Analytical, Aspirational, Anthropological)...`
  3. `[•] Synthesizing ~1,250-word structured essay...`
* **Automatic Drawer Opening:** Upon completion, the chat feed displays a summary and automatically opens the **Artifact Viewer** displaying the full essay.

### 4.5 Sandboxed In-App Artifact Viewer (Right Pane / Drawer)
* **Header Controls:**
  - Artifact Title, Word Count Pill (e.g. `1,248 words`), and View Toggle (`Rendered Preview` | `Raw Code`).
  - `[Copy Content]` and `[Download .md / .html]` buttons.
* **Secure `<iframe>` Sandbox:**
  - Rendered via `srcdoc` with strict `sandbox=""` (strictly NO `allow-same-origin`).
  - The iframe has an opaque `null` origin, physically preventing access to parent cookies, local storage, or host DOM.
  - Formatted with editorial Newsreader typography, bold section headers, and callout pull-quotes.

---

## 5. UI Loading, Timeout, and Error States

### 5.1 Local Ollama Error States

| Error Condition | Visual Representation | Recovery Action |
| :--- | :--- | :--- |
| **Ollama Daemon Unreachable** | Amber warning banner across chat stage: *"Could not connect to Ollama at localhost:11434. Please run 'ollama serve' in your terminal."* | Inline `[Retry Connection]` button. |
| **Model Not Downloaded** | Red alert banner: *"Model 'llama3.2:3b' is missing from Ollama. Run 'ollama pull llama3.2:3b' to install it."* | Inline copy button for command. |
| **Inference Timeout (> 60s)** | Notice card: *"Local model response timed out. The model may be under heavy CPU/GPU load."* | `[Retry Query]` and `[Cancel]` buttons. |

### 5.2 Empty State (New Session)
* Clean editorial header: *"What growth framework would you like to explore today?"*
* **Curated Prompt Starters (Clickable Chips):**
  - *"How does Shreyas Doshi differentiate between high-agency PMs and good execution?"*
  - *"Draft a Ship 30 for 30 essay on Product-Led Sales based on Pete Kazanjy's playbook."*
  - *"What are Elena Verna's rules for when B2B companies should launch self-serve pricing?"*
  - *"Explain the Cold Start Problem using Andrew Chen's interview."*

---

## 6. Responsive Layout Breakpoints

* **Desktop (> 1200px):** Three columns side-by-side (Sidebar 280px + Chat Feed 1fr + Artifact Drawer 520px).
* **Tablet (768px – 1199px):** Two columns (Sidebar collapsible via hamburger toggle; Artifact Viewer slides in as an overlay drawer).
* **Mobile (< 768px):** Single column (Sidebar is a slide-over sheet; Artifact Viewer opens as a full-screen modal).

---
## Addendum (audit): Information architecture, states, accessibility, decisions

**Information architecture.** Left sidebar: new session, session list, model toggle, health badges. Centre: conversation (messages → citation cards → abstention card). Right: Artifact drawer (Preview / Source, copy, download). Top: health/telemetry. Essay modal is a shortcut; the same skills are reachable by typing a request.

**Key states.** Empty (starter prompts incl. essay + HTML card) · streaming (status line → tokens, Stop button) · answered (citations) · abstention (amber/rose card, no sources) · error toast with remediation hint + request id · loading sessions · cloud disabled (tooltip explains missing key) · knowledge base indexing (health badge).

**Responsive.** Sidebar collapses, artifact drawer becomes full-width overlay below 1024 px.

**Accessibility.** Model provider is a `radiogroup` with `role="radio"`, `aria-checked`, focusable and operable with Enter/Space; icons carry text labels; colour is never the only status signal; iframe has a descriptive `title`; Ctrl/Cmd+N creates a session.

**Decisions.** (1) Artifact viewer is *scriptless* (`sandbox=""`) — least privilege; (2) no third-party requests (system font stacks; the earlier Google Fonts dependency contradicted the offline claim and the CSP); (3) errors always say what to do next; (4) cloud use is explicit and visibly labelled.
Note: the model name shown in the selector now comes from `/api/health` (it previously hard-coded a retired Claude model and was overwritten by the Ollama name on every poll).
