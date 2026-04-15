# AI Model Recommendations

This guide helps you choose the right Ollama model for email classification with cairn-mail.

## Quick Recommendations

| Use Case | Recommended Model | VRAM | Speed | Quality |
|----------|------------------|------|-------|---------|
| **Best Overall** | `llama3.2` | 4GB | Fast | Excellent |
| **Low VRAM (<4GB)** | `qwen2.5:3b` | 2GB | Fast | Good |
| **Maximum Quality** | `llama3.1:8b` | 8GB | Medium | Excellent |
| **Fastest** | `qwen2.5:1.5b` | 1.5GB | Very Fast | Acceptable |

## Tested Models

### Tier 1: Recommended

#### llama3.2 (Default)
```nix
ai.model = "llama3.2";
```
- **VRAM**: ~4GB
- **Speed**: ~2-3 seconds per message
- **Quality**: Excellent tag accuracy, understands context well
- **Best for**: Most users with modern GPUs

#### qwen2.5:3b
```nix
ai.model = "qwen2.5:3b";
```
- **VRAM**: ~2GB
- **Speed**: ~1-2 seconds per message
- **Quality**: Good accuracy, handles multiple languages
- **Best for**: Users with limited VRAM or integrated graphics

### Tier 2: Alternatives

#### mistral:7b
```nix
ai.model = "mistral:7b";
```
- **VRAM**: ~6GB
- **Speed**: ~3-4 seconds per message
- **Quality**: Very good, slightly verbose responses
- **Note**: May need lower temperature (0.2) for consistent JSON

#### llama3.1:8b
```nix
ai.model = "llama3.1:8b";
```
- **VRAM**: ~8GB
- **Speed**: ~4-5 seconds per message
- **Quality**: Excellent, best for complex classification
- **Best for**: Users prioritizing accuracy over speed

### Tier 3: Lightweight

#### qwen2.5:1.5b
```nix
ai.model = "qwen2.5:1.5b";
```
- **VRAM**: ~1.5GB
- **Speed**: <1 second per message
- **Quality**: Acceptable for simple classification
- **Best for**: Very limited hardware or bulk processing

#### phi3:mini
```nix
ai.model = "phi3:mini";
```
- **VRAM**: ~2GB
- **Speed**: ~1-2 seconds per message
- **Quality**: Good for straightforward emails
- **Note**: May struggle with ambiguous content

## Hardware Requirements

### Minimum (CPU-only)
- 8GB RAM
- Any modern CPU
- Model: `qwen2.5:1.5b` or `phi3:mini`
- Speed: 5-10 seconds per message

### Recommended (GPU)
- 8GB+ VRAM (AMD or NVIDIA)
- Model: `llama3.2`
- Speed: 2-3 seconds per message

### Optimal (High-end GPU)
- 12GB+ VRAM
- Model: `llama3.1:8b`
- Speed: 3-4 seconds per message with best quality

## Configuration Tips

### Temperature Setting

Lower temperature = more consistent, deterministic results.

```nix
ai = {
  model = "llama3.2";
  temperature = 0.3;  # Default, good balance
};
```

- `0.1-0.3`: Most consistent, best for classification
- `0.4-0.6`: Slightly more varied responses
- `0.7+`: Not recommended for classification tasks

### Multiple Models

If you have multiple GPUs or want to experiment:

```bash
# Pull multiple models
ollama pull llama3.2
ollama pull qwen2.5:3b

# Test classification quality
cairn-mail sync run --account personal --max 10
```

Then check the web UI to review classification accuracy.

## Troubleshooting

### Model Not Found
```bash
# List available models
ollama list

# Pull the model
ollama pull llama3.2
```

### Out of Memory
1. Try a smaller model (`qwen2.5:3b` or `phi3:mini`)
2. Close other GPU-intensive applications
3. Consider CPU-only mode (slower but works)

### Slow Classification
1. Ensure Ollama is using GPU:
   ```bash
   # Check GPU usage during sync
   nvidia-smi  # NVIDIA
   radeontop   # AMD
   ```
2. Try a smaller model
3. Check `OLLAMA_NUM_CTX` (context window) isn't too large

### Inconsistent JSON Responses
Some models may return malformed JSON. Solutions:
1. Lower temperature to 0.2
2. Try `llama3.2` which handles JSON well
3. Check Ollama version is up to date

## Model Comparison Table

| Model | Size | VRAM | Speed* | JSON | Multi-lang | Recommended |
|-------|------|------|--------|------|------------|-------------|
| llama3.2 | 3B | 4GB | 2-3s | Excellent | Good | **Yes** |
| llama3.1:8b | 8B | 8GB | 4-5s | Excellent | Excellent | Yes |
| qwen2.5:3b | 3B | 2GB | 1-2s | Good | Excellent | **Yes** |
| qwen2.5:1.5b | 1.5B | 1.5GB | <1s | Good | Good | Budget |
| mistral:7b | 7B | 6GB | 3-4s | Good | Good | Optional |
| phi3:mini | 3.8B | 2GB | 1-2s | Good | Limited | Budget |

*Speed measured on RTX 3080 / RX 6800 XT

## Cairn Integration

If you're using [Cairn](https://github.com/kcalvelli/cairn), Ollama is pre-configured with ROCm acceleration for AMD GPUs. The default 32K context window (`OLLAMA_NUM_CTX`) is more than sufficient for email classification.

```nix
# In your Cairn user config (e.g., keith.nix)
programs.cairn-mail = {
  enable = true;
  ai.model = "llama3.2";  # Uses Cairn's Ollama instance
};
```

No additional Ollama configuration needed - Cairn handles GPU acceleration automatically.
