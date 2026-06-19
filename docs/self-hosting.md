# Self-hosting Holo3

Holo's agent talks to any OpenAI-compatible server, so you can serve [Holo3](https://huggingface.co/Hcompany/Holo3-35B-A3B) yourself and keep every screenshot, keystroke, and bit of app content on your own machine. Point any surface at your server with `--base-url`:

```bash
holo run --base-url http://localhost:8000/v1 "Open Safari and go to hcompany.ai"
```

No `holo login` is needed in this mode, and the hosted `HAI_API_KEY` is never passed through to your server.

## Hardware

Holo3-35B-A3B fits comfortably on a recent MacBook Pro or Mac Mini at Q4. NVIDIA's [DGX Spark](https://www.nvidia.com/en-us/products/workstations/dgx-spark/) runs both the 35B and 122B at higher precision and gives you the best agent quality on a single box. Multi-GPU rigs and rack servers serve the FP8 stack at full throughput.

## vLLM (Holo3-35B-A3B-FP8)

Per-request `reasoning_effort` is honored via `chat_template_kwargs`; think tokens are decoded with `--reasoning-parser qwen3`.

```bash
export VLLM_ATTENTION_BACKEND=FLASHINFER
export TORCH_CUDA_ARCH_LIST=12.1a

vllm serve Hcompany/Holo3-35B-A3B-FP8 \
  --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size 1 --gpu-memory-utilization 0.85 \
  --max-model-len 65537 --max-num-batched-tokens 8192 --max-num-seqs 1 \
  --kv-cache-dtype fp8 --attention-backend flashinfer --enable-prefix-caching \
  --load-format fastsafetensors \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 \
  --chat-template-content-format openai \
  --limit-mm-per-prompt '{"image": 1}' \
  --mm-processor-cache-gb 4 --mm-processor-cache-type shm \
  --trust-remote-code
```

## llama.cpp (Holo3-35B-A3B GGUF)

Quants by [mradermacher/Holo3-35B-A3B-GGUF](https://huggingface.co/mradermacher/Holo3-35B-A3B-GGUF) (community).

Reasoning behavior is fixed at server launch (`--reasoning auto` separates `<think>` from content). `chat_template_kwargs` is silently ignored, so per-request `reasoning_effort` falls back to logit-bias steering on the `</think>` token.

```bash
llama-server -hf mradermacher/Holo3-35B-A3B-GGUF:Q4_K_M \
  --host 0.0.0.0 --port 8000 \
  --jinja --reasoning auto \
  -c 65536 -ngl 99 \
  --chat-template-kwargs '{"enable_thinking": true}'
```
