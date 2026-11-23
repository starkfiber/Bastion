# Control Edition observations · 0.7.0

One native-gated repository QA task passed 97 tests with execution measured at 30,656.265 ms. The fresh CLI cycle took 30,897.866 ms and receipt reuse took 306.949 ms. The two native execution gates totaled 18.83 ms. Host load and revisions differ from earlier runs; no speed advantage, regression estimate or rival comparison is established.

[Current qualification](assets/control-qualification.json) · [Definitions](TASKS.md)

## Earlier observations

# Current task observations · 0.6.0 candidate

The corrected native-backed repository QA task ran 92 tests successfully. One observation measured execution at 18,316.472 ms; the fresh CLI cycle was 18,631.887 ms and receipt reuse was 177.661 ms. Native start/outcome gates made 2 calls totaling 20.398 ms including startup. Calls inside child tests are outside that counter. This is neither a throughput benchmark nor a Python/native backend comparison. Host load was uncontrolled.

[Qualification data](assets/task-edition-qualification.json) · [Metrics definitions](TASKS.md)

## Historical 0.5 microbenchmarks

These samples were captured before Task Edition and describe its tiny pure fixture, not the current repository QA task.

# Measured local speed

These results describe this machine and tiny synthetic fixtures. They are not model-inference, autonomous-MVP, concurrency, production-capacity or competitor benchmarks.

| Operation | Median | Minimum | Maximum |
|---|---:|---:|---:|
| Plan → approve → run → verify | 210.28 ms | 192.14 ms | 328.63 ms |
| Reuse verified receipt | 50.42 ms | 46.17 ms | 68.14 ms |
| Brain query, no knowledge match | 48.38 ms | 43.30 ms | 76.93 ms |

## Method

15 samples per operation, one unrecorded `init` warm-up, macOS ARM64 and Python 3.9.6. The workflow contains one checked sum over [1,2,3]. The full cycle launches four fresh CLI processes: plan, approve, run and verify. Receipt reuse launches another fresh process; brain retrieval queries an unmatched word with no stored knowledge. No native engine or provider is configured. Host load and caches are uncontrolled. No stable tail-latency or throughput conclusion is drawn.

The previously retained 82-test local run took 6.639 seconds; that is one suite observation, not a repeated benchmark. Native qualification and code-check performance depend on the actual workload and are not represented by the tiny timing fixture.

```sh
python3 tools/measure_cli.py --samples 15 --out docs/assets/performance.json
```

[Raw samples and environment](assets/performance.json). Rerunning replaces that local report intentionally; preserve the previous report if comparing revisions.
