# Baseline Results

## Setup

- Model: openrouter/qwen/qwen3-32b
- Temperature: default (1.0)
- Tasks: 3 retail domain tasks (dev slice)
- Trials: 1

## Results

- Mean pass@1: 0.3333
- 95% CI: 0.0 to 0.7935
- Published reference: 0.42
- Gap from reference: -0.087

## Cost

- Cost per run: $0.00
- Total for baseline: $0.00
- Note: LiteLLM does not price qwen3-32b-04-28 so cost
  shows as zero. Actual spend tracked via OpenRouter dashboard.

## Latency

- p50: 111476ms
- p95: 144826ms

## Unexpected Behavior

Two failure modes observed. First, task 2 in multiple runs
failed with an OpenAI fallback error when LiteLLM attempted
to route to OpenAI after OpenRouter timeout. Fixed by setting
OPENAI_API_KEY=not-used in .env. Second, full 30-task run
was not completed due to OpenRouter credit exhaustion.
Baseline is therefore on 3 tasks rather than the target 30.

## Confidence

Moderate confidence directionally but low statistical confidence
due to small sample size of 3 tasks. The 0.33 pass@1 is
consistent with the published tau2-bench range for smaller
models and aligns with the telecom domain reference of 0.30.
