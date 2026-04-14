# Proposal: Replace Ollama with OpenAI-Compatible API Backend

## Summary

Rip out the Ollama-specific HTTP calls and replace them with standard OpenAI `/v1/chat/completions` requests. The immediate target is axios-companion's openai-gateway on mini, but any endpoint that speaks the OpenAI chat completions protocol works — vLLM, LiteLLM, llama.cpp server, whatever.

## Problem

Ollama is a resource hog for this workload. Every sync cycle fires 50–100 classification requests. Each one triggers a model load/unload cycle (`keep_alive: 0`) because leaving llama3.2 resident would eat VRAM that other things need. That's 50–100 cold starts per sync. It's slow, it thrashes GPU memory, and llama3.2's classification accuracy isn't great anyway.

The openai-gateway is already running on mini with Claude behind it. It's warm, fast, and doesn't need to load anything. The protocol is `/v1/chat/completions` — the most widely supported LLM API in existence.

## Goals

1. Replace all three Ollama call sites with OpenAI-compatible chat completions requests
2. Drop the `ollama-python` dependency from `flake.nix`
3. Update config defaults and Nix module descriptions to reflect the new backend
4. Keep the implementation generic — no axios-companion-specific code

## Non-Goals

- Changing prompt content, DFSL mechanics, or the Classification dataclass
- Adding streaming, conversation state, or tool-use capabilities
- Supporting Ollama and OpenAI simultaneously via a backend selector (just cut it)
- Touching the MCP server, web UI, database schema, or sync engine

## Call Sites

All three follow the same pattern: build a prompt string, POST it, parse JSON from the response.

### 1. `ai_classifier.py:classify()` (line ~209)

```python
# Current (Ollama)
requests.post(f"{endpoint}/api/generate", json={
    "model": model, "prompt": prompt, "format": "json",
    "stream": False, "keep_alive": 0,
    "options": {"temperature": 0.3}
})
result.get("response", "")  # raw JSON string

# Target (OpenAI)
requests.post(f"{endpoint}/v1/chat/completions", json={
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.3,
    "response_format": {"type": "json_object"}
})
choices[0]["message"]["content"]  # raw JSON string
```

### 2. `ai_classifier.py:generate_replies()` (line ~393)

Same transformation. Temperature 0.7 for creative replies.

### 3. `action_agent.py:_extract_data()` (line ~336)

Same transformation. Temperature 0.1 for structured extraction.

## Config Changes

**`modules/home-manager/default.nix`:**

| Option | Old Default | New Default | Notes |
|--------|------------|-------------|-------|
| `ai.model` | `"llama3.2"` | `"claude-sonnet-4-20250514"` | Cosmetic for gateways that ignore it; meaningful for direct vLLM/etc. |
| `ai.endpoint` | `"http://localhost:11434"` | `"http://localhost:18789"` | openai-gateway default port |
| `ai.model` description | "Ollama model to use" | "Model name for the OpenAI-compatible API" |
| `ai.endpoint` description | "Ollama API endpoint" | "OpenAI-compatible API endpoint (any /v1/chat/completions provider)" |

**`openspec/config.yaml`:** Update AI Engine line from "Ollama" to "OpenAI-compatible API" and Constraints from "Local AI Only / must run via Ollama" to reflect the new backend.

## Dependency Changes

**Drop from `flake.nix`:**
- The entire `ollama-python` package definition (~15 lines)
- The `ollama-python` entry in `propagatedBuildInputs`
- `ollama` from devShell packages

The `requests` library (already a dependency) handles the HTTP calls. No new dependencies needed.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Gateway down during sync | Classification skipped for that cycle | Existing timeout + error handling already covers this |
| `response_format: json_object` not supported by target | Malformed JSON responses | Fall back to prompting for JSON (already in prompt text); parse defensively |
| Breaking existing Ollama users | They need to switch backends | This is a small project with one user. He asked for this. |

## Success Criteria

- [ ] `classify()`, `generate_replies()`, and `_extract_data()` all hit `/v1/chat/completions`
- [ ] `ollama-python` is gone from `flake.nix`
- [ ] Nix module defaults point to OpenAI-compatible endpoint
- [ ] Sync cycle completes with the openai-gateway backend
- [ ] No references to `/api/generate` or `keep_alive` remain in source
