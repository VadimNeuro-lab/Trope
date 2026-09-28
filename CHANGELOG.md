# Changelog

## 1.0.0

First public release of the reference implementation.

### Planned for a later release

Two parts of the experimental setup are still being prepared for release:

- **Official scorers for NoveltyBench, CreativityPrism, UoT and ResearchBench.**
  Until they are added, `verify/oracle.py` scores these benchmarks with lexical
  stand-ins, and every verdict they produce carries `stand_in=True`.
- **The retrieval index behind the evidence corpus `C`.** Until it is added,
  `Nov(s|C)` is computed against the small bundled index
  (`corpus.fallback_index`, 21 passages built from `assets/frames.json`).

Numbers obtained with these substitutes are not comparable to the ones reported
in the paper.
