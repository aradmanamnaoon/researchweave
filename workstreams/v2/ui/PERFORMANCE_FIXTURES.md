# Performance and resource fixtures

All performance fixtures are deterministic, synthetic and local-only.

- **10,000-row dataset:** two columns (x, group) with integer row identifiers and alternating synthetic groups. Measures CSV parse/persistence plus a final 250-row page.
- **2,000-source library:** short local text records with one Unicode target in the final source. Measures bounded literal Unicode search.
- **Long manuscript:** repeated synthetic sentence text above 150,000 characters. Measures publication-readiness inspection without external metadata access.
- **50,000 chart observations:** deterministic floats based on index modulo 100 with 60 histogram bins. Exercises the documented chart observation limit; 50,001 is rejected in tests.
- **Large recovery journal:** repeated Unicode/Persian synthetic notes below the 250,000-character editor bound. Measures atomic save plus integrity-checked inspect.
- **ZIP bomb ratio:** a highly compressible local archive member is rejected by the snapshot decompression-ratio guard.
- **Job cancellation:** a cooperative worker observes its stop event and reaches terminal state cancelled.
- **Narrow / 200% layout:** offscreen screen matrix and accessibility tests cover narrow 900×620 and 200% scaling. Native monitor/DPI behavior remains a platform validation item.

PERFORMANCE_RESULTS.json records wall-clock time and Python allocation peaks from tracemalloc. Those memory values are Python allocations, not whole-process RSS.
