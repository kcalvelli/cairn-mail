# Design: AI-Powered Smart Replies

## Context

cairn-mail already uses Ollama for email classification. Smart replies extend this AI capability to generate contextually appropriate response suggestions. The infrastructure (Ollama connection, prompt handling, JSON parsing) is already in place.

## Goals / Non-Goals

**Goals:**
- Generate 3-4 short, contextual reply suggestions per message
- Keep replies concise (1-2 sentences max)
- Integrate seamlessly with existing reply flow
- Minimal latency (< 3 seconds)

**Non-Goals:**
- Replacing the full compose experience
- Learning from user preferences
- Multi-turn conversation understanding
- Reply templates/canned responses (this is AI-generated)

## Decisions

### Decision 1: Reply Generation Location

**Chosen:** New method in `ai_classifier.py` (reuse existing `AIClassifier` class)

**Why:**
- Reuses existing Ollama connection and error handling
- Consistent configuration (model, endpoint, temperature)
- Single place for AI logic

**Alternative considered:** Separate `ai_replies.py` module
- Rejected: Unnecessary complexity for a single method

### Decision 2: API Endpoint Design

**Chosen:** `GET /api/messages/{id}/smart-replies`

**Why:**
- RESTful resource-based design
- Cacheable (GET request)
- Message-scoped (replies for specific message)

**Response format:**
```json
{
  "replies": [
    {"id": "1", "text": "Thanks for the update. I'll review this today."},
    {"id": "2", "text": "Got it, sounds good!"},
    {"id": "3", "text": "I'll get back to you on this shortly."}
  ],
  "generated_at": "2025-01-18T12:00:00Z"
}
```

### Decision 3: When to Show Smart Replies

**Chosen:** Always fetch on message detail view, but only display for actionable messages

**Criteria to show:**
- Message has content (not empty)
- Message is not from the current user (not a sent message)
- Message is in inbox or a folder that warrants replies

**Criteria to hide:**
- Newsletters (tag: `newsletter`)
- Promotional emails (tag: `junk`)
- System notifications (tag: `dev` for CI/CD etc.)

### Decision 4: Reply Tone and Style

**Chosen:** Professional but friendly, context-aware

**Prompt strategy:**
- Analyze original message sentiment/tone
- Generate replies matching appropriate formality
- Include one casual, one neutral, one formal option when applicable
- Keep to 1-2 sentences

### Decision 5: Compose Integration

**Chosen:** Add `body` query parameter to pre-populate editor

**URL format:**
```
/compose?reply_to={id}&to={email}&subject={subject}&account_id={id}&body={encoded_reply}
```

**Why:**
- Consistent with existing pattern (subject, to, etc. already supported)
- URL-encodable
- Works with browser navigation

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Slow generation (>3s) | Show loading skeleton, cache results |
| Inappropriate suggestions | Clear "AI-generated" label, easy to dismiss |
| LLM unavailable | Graceful degradation (hide component) |
| Context misunderstanding | Keep replies generic enough to be safe |

## Component Architecture

```
MessageDetailPage
├── Message Content
├── SmartReplies (new)
│   ├── Loading skeleton (while fetching)
│   ├── Reply chips (clickable)
│   └── Error state (hidden if failed)
└── Metadata (classified_at, confidence)
```

## Data Flow

```
1. User opens message detail
2. Frontend fetches /api/messages/{id}/smart-replies
3. Backend calls AIClassifier.generate_replies(message)
4. AI generates suggestions via Ollama
5. Backend returns JSON with reply options
6. Frontend displays as clickable chips
7. User clicks chip
8. Navigate to /compose with body param
9. Compose page pre-fills editor with reply text
```

## Open Questions

1. **Caching**: Should we cache smart replies for the same message?
   - Tentative: Yes, 5-minute cache per message

2. **Regenerate option**: Should users be able to request new suggestions?
   - Tentative: v1 no, but could add "refresh" button later

3. **Loading behavior**: Show skeleton or spinner?
   - Tentative: Skeleton with 3 placeholder chips
