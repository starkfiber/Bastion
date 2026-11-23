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
