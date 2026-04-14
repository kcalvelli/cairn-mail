# Tasks: Replace Ollama with OpenAI-Compatible API Backend

## 1. Replace call sites

- [x] **1.1** `ai_classifier.py:classify()` — Replace `/api/generate` POST with `/v1/chat/completions`. Map prompt to `messages: [{role: "user", content: prompt}]`. Add `response_format: {type: "json_object"}`. Parse response from `choices[0].message.content` instead of `response`. Drop `keep_alive`, `format: "json"`, `stream`. Update error log messages from "Ollama" to something backend-agnostic.

- [x] **1.2** `ai_classifier.py:generate_replies()` — Same transformation as 1.1, keeping temperature 0.7. Update error log messages.

- [x] **1.3** `action_agent.py:_extract_data()` — Same transformation. Rename constructor params from `ollama_endpoint`/`ollama_model`/`ollama_timeout` to `ai_endpoint`/`ai_model`/`ai_timeout`. Update all references in `cli/sync.py` and `api/routes/sync.py` that pass these kwargs.

- [x] **1.4** Update `AIConfig` dataclass defaults: `model` → `"claude-sonnet-4-20250514"`, `endpoint` → `"http://localhost:18789"`. Update docstring from "Ollama" to "OpenAI-compatible API".

- [x] **1.5** Update module-level docstrings in `ai_classifier.py` and `action_agent.py` to remove Ollama references.

## 2. Update Nix config

- [x] **2.1** `modules/home-manager/default.nix` — Change `ai.model` default to `"claude-sonnet-4-20250514"`, `ai.endpoint` default to `"http://localhost:18789"`. Update description strings from "Ollama" to "OpenAI-compatible API".

- [x] **2.2** `flake.nix` — Remove `ollama-python` package definition and its entry in `propagatedBuildInputs`. Remove `ollama` from devShell packages.

## 3. Cleanup

- [x] **3.1** `openspec/config.yaml` — Update AI Engine and Constraints sections to reflect OpenAI-compatible backend instead of Ollama.

- [x] **3.2** Grep for any remaining "ollama" references in `src/` and `modules/` — update or remove. (Docs and archive are out of scope.)

- [x] **3.3** Update test mocks in `tests/ai/test_ai_classifier.py` — response shape changed from `{"response": ...}` to `{"choices": [{"message": {"content": ...}}]}`.

## Dependencies

- Tasks in group 1 are independent of each other (can be done in any order)
- Group 2 is independent of group 1
- Group 3 depends on groups 1 and 2 (cleanup sweep)

## Verification

- [x] No `ollama` imports or `/api/generate` calls remain in `src/` or `modules/`
- [ ] `nix flake check` passes (or at least `nix eval` on the flake doesn't error)
- [ ] Config generates valid YAML with new defaults
