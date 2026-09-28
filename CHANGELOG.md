# Changelog

## 1.0.0

First public release of the reference implementation.

The paper's experiments score NoveltyBench, CreativityPrism, UoT and
ResearchBench with each benchmark's official scorer, and compute `Nov(s|C)`
against the paper's evidence corpus. So that the pipeline runs offline, this
release bundles lightweight substitutes for both: scorers in `verify/oracle.py`,
flagged `stand_in=True`, and a small index in `corpus.fallback_index`. The
official scorers and the paper's corpus are planned for a later release.
