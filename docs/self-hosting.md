# Self-hosting Holo

Serve Holo yourself and keep every screenshot, keystroke, and bit of app content on your own machine. Point `holo` at any OpenAI-compatible server with `--base-url`, and name the Holo version it serves with `--model`:

```bash
holo run --base-url http://localhost:8000/v1 --model holo4-35b-a3b "Open Safari and go to hcompany.ai"
```

`--model` is both the Holo version (it sets the prompt format: `holo4-35b-a3b`, `holo4-27b`, or `holo3-1-35b-a3b`) and the model name sent to your server, so serve under that name. No `holo login` is needed, and the hosted API key is never passed to your server. For `holo mcp`, set `HAI_AGENT_RUNTIME_BASE_URL` and `HAI_AGENT_RUNTIME_MODEL` instead.

## vLLM (GPU server)

```bash
vllm serve Hcompany/Holo4-35B-A3B-FP8 \
  --served-model-name holo4-35b-a3b \
  --max-model-len 262144 \
  --enable-prefix-caching \
  --chat-template-content-format openai \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 \
  --limit-mm-per-prompt '{"image": 5, "video": 0}'
```

Base URL: `http://localhost:8000/v1`.

## llama.cpp (Mac)

```bash
brew install llama.cpp
llama-server -hf Hcompany/Holo4-35B-A3B-GGUF
```

Base URL: `http://localhost:8080/v1`. llama.cpp accepts any model name.

More sizes, precisions, and troubleshooting: [Run the model on your own GPUs](https://hub.hcompany.ai/agents-api/local-inference).
