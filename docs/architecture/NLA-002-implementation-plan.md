# Orion Natural Language Architecture — Implementation Plan

**Document:** NLA-002  
**Parent:** NLA-001 (Natural Language Architecture Proposal)  
**Author:** Phoenix Link (Pty) Ltd  
**Status:** Implementation Plan — Ready for Review  
**Created:** February 13, 2026  

---

## 1. The Core Problem

Orion sits between the user and the LLM. Today, Orion is an uneducated middleman:

```
User (speaks naturally) → Orion (pattern-matches keywords) → LLM (super-intelligent)
```

A newborn is translating between two adults. It doesn't understand what the user is saying — it matches keywords, picks a route, staples some rules on top, and forwards the raw message to a vastly more intelligent system. The quality of what reaches the Builder and Reviewer **determines the quality of the output**, and right now that input quality is poor.

### What Goes Wrong Today

| User Says | Orion Does | What Should Happen |
|-----------|-----------|-------------------|
| "I'm stuck" | No coding keywords → routes as QUESTION | Ask: "Stuck on what? A bug? A design decision?" |
| "Can you look at this?" | No file pattern → generic FAST_PATH | Ask: "Which file? What should I look for?" |
| "The deploy broke everything" | Keyword "deploy" → CODING_TASK | Acknowledge frustration first, then ask for details |
| "Make it better" | Vague → QUESTION | Ask: "Better how? Performance? Readability? UX?" |
| "Hi, can you help with auth?" | "Hi" → CONVERSATIONAL | Recognize compound intent: greeting + coding request |

The regex classifier in `fast_path.py` (`_classify_intent`) and the keyword matcher in `scout.py` cannot handle any of these. They fail on **vague input, compound intents, tone, and context**.

---

## 2. Current State — What Exists

### 2.1 Request Flow (Today)

```
User Input
  │
  ▼
Scout.analyze()                    ← Regex keyword matching
  ├─ FAST_PATH ──→ FastPath        ← _classify_intent(): more regex
  │                  ├─ CONVERSATIONAL: persona only
  │                  ├─ QUESTION: persona + repo map
  │                  └─ CODING_TASK: persona + repo map + files + platforms
  │
  ├─ COUNCIL ────→ Builder         ← Raw message + persona + constraints
  │                  → Reviewer    ← Reviews Builder output
  │                  → Governor    ← Safety check
  │
  └─ ESCALATION ─→ Human approval required
```

### 2.2 Memory System (Today)

**Tier 1 — Session Memory** (`engine.py: _session dict`)
- In-memory dict, lost on restart
- Stores: insights, patterns during session
- Used: keyword search via `recall()`
- **Gap: No conversation history. Each message is independent. Orion has zero memory of what was said 30 seconds ago.**

**Tier 2 — Project Memory** (`project.py: ProjectMemory`)
- JSON file at `{workspace}/.orion/project_memory.json`
- Stores: file index, decisions, project patterns
- Used: `get_full_context()` for LLM prompts, `get_relevant_decisions()`
- **Gap: Stores file metadata and decisions, not user interaction history. Cannot answer "what did the user ask about last time?"**

**Tier 3 — Institutional Memory** (`institutional.py: InstitutionalMemory`)
- SQLite at `~/.orion/institutional_memory.db`
- Tables: `learned_patterns`, `learned_anti_patterns`, `user_preferences`, `domain_expertise`, `execution_history`, `confirmed_feedback`
- Used: learning from outcomes, pattern retrieval
- **Gap: Stores what worked and what didn't, but has zero language understanding. Cannot parse intent, detect ambiguity, or reason about meaning.**

**Embeddings** (`embeddings.py: EmbeddingStore`)
- sentence-transformers (`all-MiniLM-L6-v2`, 80MB local model)
- Stores embeddings in `memory_embeddings` table alongside Tier 3
- Used: `recall_for_prompt()` semantic search
- **Gap: Only indexes Tier 3 memory entries. Not used for intent classification, request understanding, or clarification detection.**

**Learning Loop** (`feedback.py: LearningLoop`)
- Processes positive/negative/edit feedback
- Stores patterns in institutional + project memory
- **Gap: Learns from outcomes but doesn't influence how Orion understands the NEXT request.**

**Evolution Engine** (`evolution.py`)
- Tracks performance metrics, generates improvement guidance
- Injected into FastPath and Builder prompts
- **Gap: Self-improvement recommendations are text-based, not actionable understanding.**

### 2.3 Prompt Construction (Today, post v7.5.0 slim persona)

| Component | FastPath Tokens | Builder Tokens |
|-----------|----------------|---------------|
| Persona card | 50–120 (tiered) | ~120 |
| Memory context | ~200 (if any) | ~200 (if any) |
| Repo map | ~1024 | ~1024 |
| Platform capabilities | ~100 | N/A |
| File contents | ~5000 | ~5000 |
| Evolution guidance | ~100 | ~100 |
| **Total** | **~1500–6500** | **~1500–6500** |

The persona and context is bolted onto a raw user message. There is no understanding layer — no step where Orion asks "do I actually understand what this person wants?"

---

## 3. Target State — The Educated Orion

### 3.1 Request Flow (Proposed)

```
User Input
  │
  ▼
┌─────────────────────────────────────────────────┐
│  ORION UNDERSTANDING LAYER (new)                │
│                                                  │
│  Step 1: Context Assembly                        │
│    • Tier 1: Last N messages in this session     │
│    • Tier 2: User history + project patterns     │
│    • Tier 3: Language knowledge + intent exemplars│
│                                                  │
│  Step 2: Intent Analysis                         │
│    • Embed user message                          │
│    • Compare against intent exemplar bank         │
│    • Score confidence: "How sure am I?"           │
│    • Detect tone, urgency, compound intents       │
│                                                  │
│  Step 3: Clarification Gate                      │
│    • If confidence < threshold → ASK the user    │
│    • Targeted questions, not generic "can you     │
│      clarify?" — "Did you mean X or Y?"          │
│    • Loop until understanding is sufficient       │
│                                                  │
│  Step 4: Brief Generation                        │
│    • Structured brief for Builder/Reviewer        │
│    • Includes: intent, context, constraints,      │
│      user preferences, relevant history           │
│    • This is what the LLM actually receives       │
│                                                  │
└───────────────────┬─────────────────────────────┘
                    │ structured brief
                    ▼
              Scout (refined routing)
                ├─ FAST_PATH → FastPath (with brief)
                ├─ COUNCIL  → Builder (with brief) → Reviewer → Governor
                └─ ESCALATION → Human
```

### 3.2 The Clarification Loop

This is the single most important change. Today:

```
User: "Make it better"
Orion: [guesses what "better" means, sends to Builder, gets mediocre output]
```

After:

```
User: "Make it better"
Orion: "Better in what way? I could focus on:
        1. Performance (faster execution)
        2. Readability (cleaner code, better naming)
        3. Error handling (more robust)
        4. Test coverage
        What matters most to you?"
User: "Readability"
Orion: [builds precise brief: "Refactor for readability — improve naming,
        reduce complexity, add docstrings. Files: X, Y, Z."]
Builder: [receives clear spec, produces high-quality output]
```

**Clarification is not a failure — it's intelligence.** A senior developer asks questions before coding. A junior developer guesses and produces garbage.

### 3.3 The Brief

Today, the Builder receives:

```
System: [persona + rules]
User: "Make it better"
Context: [5000 tokens of file contents, repo map, platform capabilities]
```

After, the Builder receives:

```
System: [slim persona]
Brief: {
  "intent": "refactor_for_readability",
  "confidence": 0.95,
  "user_said": "Make it better",
  "understood_as": "Refactor for improved readability — cleaner naming,
                    reduced complexity, documentation",
  "target_files": ["src/orion/core/agents/fast_path.py"],
  "user_preferences": {
    "style": "concise, Pythonic",
    "naming": "snake_case, descriptive",
    "comments": "minimal, only for non-obvious logic"
  },
  "relevant_history": [
    "Previously refactored builder.py — user approved (5/5)",
    "User rejected verbose docstrings (2/5)"
  ],
  "constraints": "Do not change public API signatures"
}
```

The difference: the LLM gets a **precise specification** instead of a vague message with context dumped on top.

---

## 4. The English Foundation Layer (Tier 3 Enhancement)

### 4.1 What It Is

The English Foundation is a curated knowledge base stored in Tier 3 that gives Orion its own understanding of language. It has four components:

### 4.2 Component A: Semantic Grounding (Dictionary)

**Purpose:** Give Orion explicit word/phrase meanings it can reason about independently of the LLM.

**Storage:** New SQLite table `semantic_dictionary` in `institutional_memory.db`

```sql
CREATE TABLE semantic_dictionary (
    term TEXT PRIMARY KEY,
    definition TEXT,
    part_of_speech TEXT,        -- noun, verb, adjective, etc.
    synonyms TEXT,              -- JSON array
    antonyms TEXT,              -- JSON array
    domain_tags TEXT,           -- JSON array: ["coding", "general", "emotional"]
    usage_examples TEXT,        -- JSON array of example sentences
    ambiguity_score REAL        -- 0.0 (unambiguous) to 1.0 (highly ambiguous)
);
```

**Scope:** Not a full dictionary. A curated set of:
- ~500 coding-domain terms ("refactor", "deploy", "debug", "lint", "test")
- ~300 conversational terms ("help", "stuck", "better", "wrong", "confused")
- ~200 ambiguous terms that commonly cause misclassification ("it", "this", "that", "fix", "change")

**Why not rely on the LLM?** Because the LLM is downstream. Orion needs to understand the request BEFORE it talks to the LLM. The dictionary is Orion's own knowledge, not a pass-through.

### 4.3 Component B: Intent Exemplar Bank

**Purpose:** Replace regex patterns with semantic similarity matching against real examples.

**Storage:** New SQLite table `intent_exemplars` in `institutional_memory.db`

```sql
CREATE TABLE intent_exemplars (
    id TEXT PRIMARY KEY,
    user_message TEXT,          -- "Hi, how are you?"
    intent TEXT,                -- "conversational"
    sub_intent TEXT,            -- "greeting"
    confidence REAL,            -- how clearly this maps to the intent
    embedding BLOB,             -- pre-computed embedding vector
    source TEXT,                -- "curated", "learned_from_feedback"
    created_at TEXT
);
```

**Initial seed:** ~200 curated exemplars across intents:

| Intent | Sub-Intent | Example Count |
|--------|-----------|---------------|
| conversational | greeting | 15 |
| conversational | farewell | 10 |
| conversational | gratitude | 10 |
| conversational | identity | 10 |
| question | code_explanation | 20 |
| question | architecture | 15 |
| question | debugging | 15 |
| question | general_knowledge | 10 |
| coding | create_file | 15 |
| coding | modify_file | 15 |
| coding | fix_bug | 15 |
| coding | refactor | 10 |
| coding | test_write | 10 |
| compound | greeting_plus_task | 15 |
| ambiguous | needs_clarification | 15 |

**How it works:**
1. Embed user message using `EmbeddingStore.embed_text()`
2. Find top-5 nearest exemplars by cosine similarity
3. If top match similarity > 0.85 → high confidence, route directly
4. If top match similarity 0.60–0.85 → medium confidence, may need clarification
5. If top match similarity < 0.60 → low confidence, definitely ask for clarification

**Growth:** The exemplar bank grows over time. When a user provides feedback (positive or negative), the original request + correct intent gets added as a new exemplar. Orion literally learns from every conversation.

### 4.4 Component C: Contextual Usage Patterns

**Purpose:** Understand how words change meaning in context.

**Storage:** New SQLite table `usage_patterns` in `institutional_memory.db`

```sql
CREATE TABLE usage_patterns (
    id TEXT PRIMARY KEY,
    phrase TEXT,                 -- "look at this"
    context_type TEXT,           -- "with_file_reference", "standalone"
    typical_intent TEXT,         -- "code_review" vs "general_question"
    confidence REAL,
    occurrence_count INTEGER,
    last_seen TEXT
);
```

**Examples:**

| Phrase | Context | Typical Intent |
|-------|---------|---------------|
| "look at this" | + file path mentioned | code_review |
| "look at this" | standalone | needs_clarification |
| "fix this" | + error message | fix_bug |
| "fix this" | standalone | needs_clarification |
| "it's broken" | after coding discussion | fix_bug |
| "it's broken" | first message in session | needs_clarification |

### 4.5 Component D: Tone & Urgency Detection

**Purpose:** Detect emotional tone and urgency to adjust response style.

**Storage:** Lightweight — no separate table. Uses embedding similarity against tone exemplars stored in the intent exemplar bank with special `tone_` prefix intents.

**Tone categories:**
- `casual` — "hey, can you tweak this?"
- `formal` — "Please implement the authentication module"
- `frustrated` — "This still doesn't work!"
- `urgent` — "Production is down, need fix NOW"
- `exploratory` — "What if we tried a different approach?"
- `grateful` — "Thanks, that's perfect"

**How it's used:** Tone doesn't change routing — it changes response style. A frustrated user gets acknowledgment before solutions. An urgent request skips pleasantries.

---

## 5. Conversation History (Tier 1 Enhancement)

### 5.1 The Gap

Today, Tier 1 is a dict of `MemoryEntry` objects with no structure. Each message is independent. Orion cannot:
- Reference what was said earlier in the conversation
- Detect follow-up questions ("and what about the tests?")
- Maintain context across a multi-turn dialogue

### 5.2 The Solution: Conversation Buffer

**New class:** `ConversationBuffer` in `engine.py`

```python
@dataclass
class ConversationTurn:
    role: str           # "user" or "orion"
    content: str
    timestamp: str
    intent: str         # classified intent for this turn
    clarification: bool # was this a clarification exchange?

class ConversationBuffer:
    """Sliding window of recent conversation turns."""
    
    def __init__(self, max_turns: int = 20):
        self.turns: list[ConversationTurn] = []
        self.max_turns = max_turns
    
    def add(self, role: str, content: str, intent: str = "", clarification: bool = False):
        ...
    
    def get_context_window(self, n: int = 5) -> list[ConversationTurn]:
        """Last N turns for prompt injection."""
        ...
    
    def get_last_user_intent(self) -> str | None:
        """What was the user's last classified intent?"""
        ...
    
    def is_follow_up(self, current_message: str) -> bool:
        """Detect if current message is a follow-up to previous."""
        ...
```

**Integration:** The `ConversationBuffer` is held by the REPL session and passed into the Understanding Layer. It provides the "what did we just talk about?" context that's currently missing.

---

## 6. The Understanding Layer — Technical Design

### 6.1 New Module: `src/orion/core/understanding/`

```
src/orion/core/understanding/
├── __init__.py
├── analyzer.py          # Main entry point — RequestAnalyzer class
├── intent_classifier.py # Embedding-based intent classification
├── clarification.py     # Clarification detection and question generation
├── brief_builder.py     # Structured brief generation for Builder/Reviewer
└── foundation.py        # English Foundation query layer
```

### 6.2 RequestAnalyzer (Main Entry Point)

```python
@dataclass
class RequestUnderstanding:
    """Orion's understanding of what the user wants."""
    
    raw_input: str                    # original user message
    intent: str                       # classified intent
    sub_intent: str                   # more specific classification
    confidence: float                 # 0.0–1.0
    tone: str                         # casual, formal, frustrated, etc.
    is_follow_up: bool                # references previous conversation
    needs_clarification: bool         # confidence too low to act
    clarification_questions: list[str] # what to ask if clarification needed
    understood_as: str                # human-readable restatement
    relevant_memories: list[str]      # from all 3 tiers
    user_preferences: dict            # from Tier 3
    conversation_context: list[dict]  # recent turns

class RequestAnalyzer:
    """
    The educated middleman. Understands user requests before routing.
    
    Replaces: regex _classify_intent() in fast_path.py
    Replaces: keyword SIMPLE_PATTERNS/COMPLEX_PATTERNS in scout.py
    """
    
    def __init__(self, memory_engine: MemoryEngine, conversation: ConversationBuffer):
        self.memory = memory_engine
        self.conversation = conversation
        self.classifier = IntentClassifier()
        self.clarifier = ClarificationDetector()
        self.foundation = EnglishFoundation()
    
    async def analyze(self, user_message: str) -> RequestUnderstanding:
        """
        Full analysis pipeline:
        1. Query conversation history (is this a follow-up?)
        2. Classify intent via embeddings
        3. Check confidence — does Orion understand?
        4. If unsure, generate clarification questions
        5. Build understanding object
        """
        ...
```

### 6.3 IntentClassifier (Replaces Regex)

```python
class IntentClassifier:
    """
    Embedding-based intent classification.
    
    Replaces: _CONVERSATIONAL_PATTERNS, _CODING_PATTERNS in fast_path.py
    Replaces: SIMPLE_PATTERNS, COMPLEX_PATTERNS, DANGER_PATTERNS in scout.py
    """
    
    def __init__(self):
        self.embedding_store = EmbeddingStore()
    
    def classify(self, message: str, conversation_context: list = None) -> tuple[str, str, float]:
        """
        Returns: (intent, sub_intent, confidence)
        
        Uses cosine similarity against intent exemplar bank.
        Falls back to keyword matching if embeddings unavailable.
        """
        ...
```

### 6.4 ClarificationDetector

```python
class ClarificationDetector:
    """
    Determines when Orion should ask for clarification instead of guessing.
    
    Triggers:
    - Low intent confidence (< 0.65)
    - Ambiguous pronouns without clear referent ("fix this", "look at it")
    - Vague qualifiers without specifics ("make it better", "improve it")
    - Missing required context (no file specified for file operations)
    - Compound intents that need decomposition
    """
    
    def needs_clarification(self, understanding: RequestUnderstanding) -> bool:
        ...
    
    def generate_questions(self, understanding: RequestUnderstanding) -> list[str]:
        """
        Generate targeted clarification questions.
        
        NOT: "Can you please clarify?"
        YES: "Did you mean the authentication module or the user profile module?"
        YES: "Better how? I could focus on performance, readability, or error handling."
        """
        ...
```

### 6.5 BriefBuilder

```python
@dataclass
class TaskBrief:
    """Structured brief that replaces raw user message for Builder/Reviewer."""
    
    intent: str
    confidence: float
    user_said: str
    understood_as: str
    target_files: list[str]
    user_preferences: dict
    relevant_history: list[str]
    constraints: list[str]
    tone: str
    priority: str  # normal, urgent

class BriefBuilder:
    """
    Builds structured briefs for downstream agents.
    
    This is the key quality improvement — instead of forwarding
    a raw user message, Orion sends a precise specification.
    """
    
    def build(self, understanding: RequestUnderstanding, scout_report=None) -> TaskBrief:
        ...
    
    def to_prompt(self, brief: TaskBrief) -> str:
        """Format brief as a prompt section for the LLM."""
        ...
```

---

## 7. Integration Points — What Changes Where

### 7.1 Files Modified

| File | Change | Complexity |
|------|--------|-----------|
| `core/memory/engine.py` | Add `ConversationBuffer`, wire into `recall_for_prompt` | Medium |
| `core/memory/institutional.py` | Add new tables: `semantic_dictionary`, `intent_exemplars`, `usage_patterns` | Medium |
| `core/memory/embeddings.py` | Add `classify_intent()` method using exemplar bank | Medium |
| `core/agents/scout.py` | Replace regex with `RequestAnalyzer.analyze()` | High |
| `core/agents/fast_path.py` | Replace `_classify_intent()` with Understanding Layer output | High |
| `core/agents/builder.py` | Accept `TaskBrief` instead of raw message | Medium |
| `core/agents/reviewer.py` | Receive brief context for better review | Low |
| `cli/repl.py` | Maintain `ConversationBuffer`, handle clarification loop | High |
| `api/routes/chat.py` | Same clarification loop for WebSocket | Medium |
| `core/learning/feedback.py` | Feed correct intents back into exemplar bank | Medium |

### 7.2 New Files

| File | Purpose |
|------|---------|
| `core/understanding/__init__.py` | Module init |
| `core/understanding/analyzer.py` | `RequestAnalyzer` — main entry point |
| `core/understanding/intent_classifier.py` | Embedding-based intent classification |
| `core/understanding/clarification.py` | Clarification detection + question generation |
| `core/understanding/brief_builder.py` | Structured brief generation |
| `core/understanding/foundation.py` | English Foundation query layer |
| `data/seed/intent_exemplars.json` | Initial seed data for exemplar bank |
| `data/seed/semantic_dictionary.json` | Initial seed data for dictionary |
| `data/seed/usage_patterns.json` | Initial seed data for usage patterns |
| `tests/unit/test_understanding.py` | Unit tests for Understanding Layer |
| `tests/unit/test_intent_classifier.py` | Intent classification accuracy tests |
| `tests/unit/test_clarification.py` | Clarification detection tests |

### 7.3 Files NOT Changed

| File | Why |
|------|-----|
| `core/agents/governor.py` | Safety layer — independent of understanding |
| `core/agents/reviewer.py` | Minimal change — just receives richer context |
| `core/persona.py` | Slim persona cards remain as-is |
| `core/editing/formats.py` | Edit format selection unchanged |
| `core/governance/` | AEGIS governance unchanged |
| `security/` | Security layer unchanged |
| `integrations/` | Platform integrations unchanged |

---

## 8. Implementation Phases

### Phase 1: Foundation + Conversation Memory (Weeks 1–4)

**Goal:** Give Orion a memory of the conversation and a bank of intent examples.

**Week 1–2: Conversation Buffer + Intent Exemplar Bank**
- [ ] Create `ConversationBuffer` class in `engine.py`
- [ ] Wire `ConversationBuffer` into REPL session lifecycle
- [ ] Wire `ConversationBuffer` into WebSocket chat handler
- [ ] Design intent exemplar schema
- [ ] Create seed data: `data/seed/intent_exemplars.json` (~200 exemplars)
- [ ] Add `intent_exemplars` table to `institutional.py`
- [ ] Write loader to seed exemplar bank on first run

**Week 3–4: Embedding-Based Intent Classifier**
- [ ] Create `core/understanding/intent_classifier.py`
- [ ] Implement `classify()` using `EmbeddingStore` against exemplar bank
- [ ] Implement confidence scoring (high/medium/low thresholds)
- [ ] Add keyword fallback for when embeddings are unavailable
- [ ] Write `tests/unit/test_intent_classifier.py` with accuracy benchmarks
- [ ] **Milestone: Intent classifier achieves >85% accuracy on test set**

**Deliverable:** Orion can classify intent via semantic similarity instead of regex, and maintains conversation history within a session.

### Phase 2: Clarification Loop + Brief Generation (Weeks 5–8)

**Goal:** Orion asks for clarification when unsure, and generates structured briefs.

**Week 5–6: Clarification Detection**
- [ ] Create `core/understanding/clarification.py`
- [ ] Implement ambiguity detection (low confidence, vague pronouns, missing context)
- [ ] Implement targeted question generation (not generic "please clarify")
- [ ] Wire clarification loop into REPL (`_clarification_exchange()`)
- [ ] Wire clarification loop into WebSocket chat
- [ ] Write `tests/unit/test_clarification.py`
- [ ] **Milestone: Orion asks clarifying questions for ambiguous inputs instead of guessing**

**Week 7–8: Brief Builder + Integration**
- [ ] Create `core/understanding/brief_builder.py`
- [ ] Implement `TaskBrief` dataclass and `BriefBuilder.build()`
- [ ] Create `core/understanding/analyzer.py` — wire everything together
- [ ] Modify `scout.py` to use `RequestAnalyzer` instead of regex
- [ ] Modify `fast_path.py` to accept `TaskBrief`
- [ ] Modify `builder.py` to accept `TaskBrief`
- [ ] Write integration tests
- [ ] **Milestone: End-to-end flow uses Understanding Layer**

**Deliverable:** Complete Understanding Layer operational — Orion understands, asks when unsure, and sends precise briefs to Builder/Reviewer.

### Phase 3: English Foundation + Learning Loop (Weeks 9–12)

**Goal:** Deepen Orion's language understanding and close the learning loop.

**Week 9–10: Semantic Dictionary + Usage Patterns**
- [ ] Create `core/understanding/foundation.py`
- [ ] Design and create seed data: `data/seed/semantic_dictionary.json` (~1000 terms)
- [ ] Design and create seed data: `data/seed/usage_patterns.json` (~200 patterns)
- [ ] Add `semantic_dictionary` and `usage_patterns` tables to `institutional.py`
- [ ] Integrate foundation queries into `RequestAnalyzer`
- [ ] Add tone detection using tone exemplars
- [ ] Write tests for foundation queries

**Week 11–12: Learning Loop Closure + Benchmarking**
- [ ] Modify `LearningLoop.process_feedback()` to add correct intent as new exemplar
- [ ] Implement exemplar confidence decay (old unused exemplars fade)
- [ ] Implement usage pattern learning from conversation history
- [ ] Create benchmark suite: 200+ test messages with expected intents
- [ ] Benchmark: intent accuracy, token usage, processing time
- [ ] Document: architecture guide, API reference, migration notes
- [ ] **Milestone: >90% intent accuracy, 30–50% token reduction, <500ms processing**

**Deliverable:** Fully educated Orion with self-improving language understanding.

---

## 9. Success Metrics & Benchmarks

### 9.1 Quantitative Targets

| Metric | Current (v7.5.0) | Phase 1 Target | Phase 3 Target |
|--------|------------------|----------------|----------------|
| Intent accuracy | ~60% (regex) | >85% (embedding) | >90% (foundation) |
| Token usage (avg) | ~3000/request | ~2500/request | ~1500–2000/request |
| Processing overhead | <1ms (regex) | <200ms (embedding) | <500ms (full pipeline) |
| Clarification rate | 0% (never asks) | 15–20% of ambiguous | 10–15% (smarter) |
| User satisfaction | unknown | measurable via feedback | >80% approval rate |

### 9.2 Qualitative Targets

- **Natural conversation:** "Hi Orion" gets a greeting, not a capability dump ✓ (already fixed)
- **Intelligent clarification:** Vague requests trigger targeted questions, not guesses
- **Context awareness:** Follow-up messages understood in context of conversation
- **Tone matching:** Frustrated users get acknowledged, casual users get casual responses
- **Precise briefs:** Builder receives structured specifications, not raw messages

### 9.3 Benchmark Test Suite

A set of 200+ test messages, categorized:

```
tests/benchmarks/
├── intent_accuracy.json      # message → expected intent
├── clarification_needed.json # ambiguous messages that should trigger questions
├── compound_intents.json     # multi-intent messages
├── follow_ups.json           # messages that depend on previous context
└── tone_detection.json       # messages with clear emotional tone
```

Each benchmark run produces a report comparing against targets.

---

## 10. Technical Considerations

### 10.1 Performance Budget

```
┌──────────────────────────────┬──────────────┐
│ Step                         │ Target Time  │
├──────────────────────────────┼──────────────┤
│ Conversation buffer query    │ <5ms         │
│ Message embedding            │ <50ms        │
│ Exemplar bank search         │ <100ms       │
│ Foundation query             │ <50ms        │
│ Clarification detection      │ <20ms        │
│ Brief generation             │ <50ms        │
│ TOTAL (no clarification)     │ <275ms       │
│                              │              │
│ LLM call for clarification   │ <2000ms      │
│ TOTAL (with clarification)   │ <2300ms      │
└──────────────────────────────┴──────────────┘
```

### 10.2 Storage

| Component | Storage | Size Estimate |
|-----------|---------|---------------|
| Conversation buffer | RAM | ~50KB per session |
| Intent exemplars | SQLite (Tier 3 DB) | ~500KB initial, grows |
| Semantic dictionary | SQLite (Tier 3 DB) | ~2MB |
| Usage patterns | SQLite (Tier 3 DB) | ~200KB initial, grows |
| Embeddings (exemplars) | SQLite (Tier 3 DB) | ~5MB (200 exemplars × 384-dim vectors) |

### 10.3 Graceful Degradation

If `sentence-transformers` is not installed:
- Intent classifier falls back to keyword matching (current behavior)
- Clarification detection uses rule-based heuristics
- Brief builder still works (less precise, but functional)
- Foundation queries return empty (no impact on routing)

The system MUST remain functional without the embedding model. Enhanced understanding is additive, not required.

### 10.4 Seed Data Versioning

Seed data ships with Orion releases in `data/seed/`. On first run (or upgrade), the loader merges seed data with existing learned data, preserving user-specific learnings. Seed data has a `source: "curated"` tag; learned data has `source: "learned_from_feedback"`. Curated data can be refreshed on upgrade without overwriting learned data.

---

## 11. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Embedding model too large for user's machine | Can't classify intents | Graceful fallback to keyword matching |
| Clarification loop annoying for experienced users | User frustration | Confidence threshold adjustable; learned patterns reduce clarification over time |
| Seed data doesn't cover user's domain | Poor initial accuracy | Fast learning from feedback; exemplar bank grows with every interaction |
| Processing overhead too high | Slow response | Caching, async embedding, lazy model loading (already implemented) |
| Brief format not understood by LLM | Bad Builder output | Brief is natural language, not structured format — LLMs handle it natively |
| Breaking change to Scout/FastPath API | Existing integrations break | Analyzer wraps existing interfaces; old API remains as fallback |

---

## 12. Migration Path

### 12.1 Backward Compatibility

The Understanding Layer is an **opt-in wrapper**, not a replacement. During transition:

1. `RequestAnalyzer.analyze()` is the new entry point
2. If it fails or is unavailable, Scout falls back to regex (current behavior)
3. Feature flag: `ORION_NLA_ENABLED=true` enables the new pipeline
4. Default: enabled after Phase 2 validation

### 12.2 Data Migration

No data migration needed. New tables are additive to the existing `institutional_memory.db`. Existing patterns, anti-patterns, and preferences remain intact and are queried by the Understanding Layer.

---

## 13. Summary

| What | Before (v7.5.0) | After (NLA) |
|------|-----------------|-------------|
| Intent detection | Regex keyword matching | Embedding similarity + exemplar bank |
| Ambiguity handling | Guess and hope | Ask targeted clarification questions |
| Conversation context | Zero (each message independent) | Sliding window of recent turns |
| What Builder receives | Raw user message + rules | Structured brief with context |
| Language understanding | None (Orion is an empty shell) | English Foundation (dictionary + patterns + embeddings) |
| Learning | Outcomes only (what worked) | Outcomes + intent correction + preference learning |
| User experience | Mechanical, prone to misclassification | Conversational, intelligent, asks when unsure |

**The fundamental shift:** Orion stops being a dumb pipe between the user and the LLM. It becomes an educated intermediary that understands what the user wants, asks when it doesn't, and gives the LLM a precise specification to work from.
