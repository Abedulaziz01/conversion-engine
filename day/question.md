# Evaluation and Statistics

## Final sharpened question

How should I compute and report uncertainty for this repo's benchmark results so that claims based on `eval/score_log.json`, `eval/baseline.md`, and the latency summaries produced by `eval/harness.py` are statistically defensible? More specifically: when comparing two versions of the conversion agent, when is a simple bootstrap confidence interval enough, when do I need a paired bootstrap over the same task set, and how would that choice change the way I write about p50/p95 latency and success-rate improvements in my evaluation summary?

## Connection to my existing artifact

This gap is grounded in the evaluation layer I already shipped for the conversion engine, especially [eval/baseline.md](/C:/Users/user/Desktop/mll/week10/conversion-engine/eval/baseline.md), [eval/harness.py](/C:/Users/user/Desktop/mll/week10/conversion-engine/eval/harness.py), and [eval/score_log.json](/C:/Users/user/Desktop/mll/week10/conversion-engine/eval/score_log.json). Right now those artifacts report point estimates like evaluated simulations, success rate, and p50/p95 latency, but they do not explain how much uncertainty surrounds those numbers or whether differences between two runs are likely real versus noise from task sampling. Closing this gap would let me revise the evaluation narrative so I can defend any benchmark comparison I make, instead of presenting single-run metrics as if they were self-evidently stable.

## Why this is worth a day's research

This is a specific mechanism gap, not a vague stats question. It matters for many agent evaluations because most benchmark writeups report a win or regression without showing whether the comparison is statistically meaningful. It is also narrow enough for a 600-1,000 word explainer with one concrete demo: resampling the existing task-level results from this repo to show how unpaired and paired bootstrap intervals lead to different conclusions.
