```markdown
# <benchmark/run> CSB Analysis

## Result Identity
- run:
- benchmark:
- kernel:
- host/architecture:
- result artifacts:

## Performance Degradation
In benchmark `<name>` we observe that performance starts degradating when `<execution-unit>` is >= `<Y>`.

| execution units | <prime-metric> | vs baseline | vs peak | success | latency | notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |

## Monitor Correlation
Monitor values that inversely increase as performance degradates:

| monitor | baseline | peak | degradation point | largest count | relation | interpretation |
| --- | ---: | ---: | ---: | ---: | --- | --- |

Monitor values that directly decrease as performance degradates:

| monitor | baseline | peak | degradation point | largest count | relation | interpretation |
| --- | ---: | ---: | ---: | ---: | --- | --- |

Other monitor signals:

| monitor | movement | interpretation |
| --- | --- | --- |

## Widening Kernel Functions
These are the functions where more cycles/samples/wait appear as execution units increase:

| function | evidence | source path | local history | notes |
| --- | --- | --- | --- | --- |

## Kernel Change Artifacts
- `<function>`: `[kernel changes](<benchmark>-<function>-kernel-changes.md)`

## Kernel Patch Artifact
- patch series:
- patch file:
- safety/implications:
- patch confidence:
- validation matrix:

## Hypothesis
State the likely bottleneck, confidence, and evidence limitations.

## Evidence Gaps
List missing artifacts, permissions, source trees, symbols, or follow-up data needed to confirm or reject the hypothesis.
```
