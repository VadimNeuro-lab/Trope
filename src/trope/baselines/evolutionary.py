"""Evolutionary and multi-regime baselines: FunSearch, PromptBreeder, EvoPrompt, Eureka, Universe of Thoughts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from trope.baselines.common import (
    BaselineContext,
    BaselineResult,
    build_prompt,
    excerpt,
    generator_params,
    rounds,
    sample_candidates,
)
from trope.baselines.search import value_score
from trope.data.base import Problem

FUNSEARCH_ISLANDS = 4
POPULATION = 8
GENERATIONS = 8
EUREKA_SAMPLES = 8

REGIMES: tuple[str, ...] = ("exploratory", "combinatorial", "transformational")

THINKING_STYLES: tuple[str, ...] = (
    "Work backwards from what a correct answer would have to satisfy.",
    "Name the quantities and the constraints before computing anything.",
    "Look for a simpler instance of the same problem and generalise it.",
    "Check whether a symmetry or an invariant makes most of the work vanish.",
    "Restate the problem in your own words, then solve the restatement.",
    "List what is given, what is asked, and what connects them.",
    "Estimate the answer first, then compute it and compare.",
    "Split the problem into the smallest steps you can verify one at a time.",
)

MUTATION_PROMPTS: tuple[str, ...] = (
    "Make the instruction more specific about the first move to make.",
    "Rewrite the instruction so it demands a check of the final answer.",
    "Add a warning about the mistake this kind of problem usually invites.",
    "Shorten the instruction to its most useful sentence.",
    "Turn the instruction into a question the solver must answer first.",
    "Combine the instruction with a demand for an explicit intermediate result.",
)

MIN_VARIATION_CHARS = 12
MAX_VARIATION_CHARS = 400


def parse_variation(text: str, marker: str) -> str | None:
    """The body of the last `marker:` line of a variation reply, or None."""
    key = marker.strip().rstrip(":").casefold()
    found: str | None = None
    for line in text.splitlines():
        head, sep, tail = line.strip().lstrip("*-#> ").partition(":")
        if sep and head.strip().casefold() == key:
            found = tail
    if found is None:
        return None
    body = " ".join(found.split()).strip(" \"'`*")
    if len(body) < MIN_VARIATION_CHARS or "\\boxed" in body:
        return None
    return excerpt(body, MAX_VARIATION_CHARS)


def _variation_prompt(problem: Problem, body: str, marker: str) -> str:
    """A prompt that asks for a rewritten artefact rather than a solution."""
    return (
        f"<problem>\n{problem.text.strip()}\n</problem>\n\n"
        f"{body.strip()}\n\n"
        f'End your reply with a single line beginning "{marker}" containing '
        "only the result, and write nothing after it.\n"
    )


def _variation_call(ctx: BaselineContext, body: str, marker: str) -> str | None:
    """One backbone variation call, charged to K like any other."""
    stats = ctx.meta.setdefault(
        "variation_calls", {"calls": 0, "parsed": 0, "unparsed": 0, "skipped": 0}
    )
    gen = ctx.ask(_variation_prompt(ctx.problem, body, marker))
    if gen is None:
        stats["skipped"] += 1
        return None
    stats["calls"] += 1
    parsed = parse_variation(gen.text, marker)
    stats["parsed" if parsed is not None else "unparsed"] += 1
    return parsed


def funsearch(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
    *,
    islands: int = FUNSEARCH_ISLANDS,
) -> BaselineResult:
    """FunSearch (Romera-Paredes et al. 2024) over four islands."""
    islands = max(1, int(islands))
    requested = budget
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=requested,
        rng=rng,
        params=generator_params(),
    )
    pools: list[list[dict[str, Any]]] = [[] for _ in range(islands)]
    reset_every = max(islands, ctx.budget // 2)
    resets = 0
    for step in rounds(ctx):
        island = (step - 1) % islands
        produced = sample_candidates(
            ctx,
            build_prompt(problem, _funsearch_guidance(pools[island])),
            iteration=step,
            meta={"island": island},
        )
        if not produced:
            break
        pools[island].append(produced[0])
        if step % reset_every == 0 and step < ctx.budget:
            resets += int(_reset_islands(pools, rng))
    return ctx.result(
        arm="funsearch",
        islands=islands,
        island_sizes=[len(pool) for pool in pools],
        resets=resets,
        reset_every=reset_every,
        matched_budget=True,
        budget_requested=requested,
        budget_granted=ctx.budget,
    )


def _funsearch_guidance(pool: Sequence[dict[str, Any]], keep: int = 2) -> str:
    if not pool:
        return (
            "Write a first solution. Keep it simple enough that its weakest step "
            "is obvious."
        )
    ranked = sorted(pool, key=lambda c: c["verdict"], reverse=True)[:keep]
    shown = "\n\n".join(
        f"[previous attempt, score {c['verdict']:.2f}]\n{excerpt(c['text'])}"
        for c in ranked
    )
    return (
        f"Here are the best attempts so far.\n\n{shown}\n\n"
        "Write a new attempt that improves on them. Do not repeat one of them "
        "with different wording; change the step that is actually costing them."
    )


def _reset_islands(pools: list[list[dict[str, Any]]], rng: np.random.Generator) -> bool:
    """Wipe the weaker half of the islands, reseed each from a survivor's best."""
    if len(pools) < 2:
        return False
    scores = [max((c["verdict"] for c in pool), default=-1.0) for pool in pools]
    order = sorted(range(len(pools)), key=lambda i: scores[i], reverse=True)
    survivors = order[: max(1, len(pools) // 2)]
    donors = [pools[i] for i in survivors if pools[i]]
    if not donors:
        return False
    for index in order[len(survivors) :]:
        donor = donors[int(rng.integers(len(donors)))]
        pools[index] = [max(donor, key=lambda c: c["verdict"])]
    return True


def promptbreeder(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
    *,
    population: int = POPULATION,
    generations: int = GENERATIONS,
) -> BaselineResult:
    """PromptBreeder (Fernando et al. 2023): a self-referential prompt population."""
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=budget,
        rng=rng,
        params=generator_params(),
    )
    units = [_seed_unit(rng, i) for i in range(max(1, population))]
    best_ever: tuple[float, dict[str, str]] | None = None
    tournaments = 0
    generations_run = 0
    for generation in rounds(ctx):
        produced = sample_candidates(
            ctx,
            [build_prompt(problem, unit["style"]) for unit in units],
            iteration=generation,
            meta={"generation": generation},
        )
        if not produced:
            break
        generations_run += 1
        fitness = [c["verdict"] for c in produced]
        for unit, score, candidate in zip(units, fitness, produced, strict=False):
            candidate["meta"]["instruction"] = unit["style"]
            if best_ever is None or score > best_ever[0]:
                best_ever = (score, dict(unit))
        if len(produced) < len(units) or ctx.remaining <= 0:
            break
        tournaments += _tournament(ctx, units, fitness, rng, best_ever)
    return ctx.result(
        arm="promptbreeder",
        population=len(units),
        nominal_generations=generations,
        generations=generations_run,
        tournaments=tournaments,
        best_instruction=(best_ever[1]["style"] if best_ever else None),
        mutation="LLM-driven, charged to K; catalogue recombination as fallback",
    )


def _seed_unit(rng: np.random.Generator, index: int) -> dict[str, str]:
    """One PromptBreeder unit: a task-prompt and the mutation-prompt that owns it."""
    return {
        "style": THINKING_STYLES[index % len(THINKING_STYLES)],
        "mutation": MUTATION_PROMPTS[int(rng.integers(len(MUTATION_PROMPTS)))],
    }


def _tournament(
    ctx: BaselineContext,
    units: list[dict[str, str]],
    fitness: Sequence[float],
    rng: np.random.Generator,
    best_ever: tuple[float, dict[str, str]] | None,
) -> int:
    """Binary tournaments over a random pairing; losers become mutated winners."""
    order = list(rng.permutation(len(units)))
    played = 0
    for i in range(0, len(order) - 1, 2):
        a, b = int(order[i]), int(order[i + 1])
        winner, loser = (a, b) if fitness[a] >= fitness[b] else (b, a)
        units[loser] = _mutate(ctx, units[winner], units, rng, best_ever)
        played += 1
    return played


def _mutate(
    ctx: BaselineContext,
    unit: dict[str, str],
    units: Sequence[dict[str, str]],
    rng: np.random.Generator,
    best_ever: tuple[float, dict[str, str]] | None,
) -> dict[str, str]:
    """One of the four PromptBreeder mutation families, as an LLM call."""
    kind = int(rng.integers(4))
    if kind == 2 and best_ever is None:
        kind = 3
    marker = "Rule" if kind == 3 else "Instruction"
    text = _variation_call(ctx, _mutation_body(kind, unit, units, best_ever), marker)
    if text is None:
        return _mutate_from_catalogue(kind, unit, units, rng, best_ever)
    if kind == 3:
        return {"style": unit["style"], "mutation": text}
    return {"style": text, "mutation": unit["mutation"]}


def _mutation_body(
    kind: int,
    unit: dict[str, str],
    units: Sequence[dict[str, str]],
    best_ever: tuple[float, dict[str, str]] | None,
) -> str:
    """The instruction PromptBreeder gives the backbone for one mutation family."""
    if kind == 0:
        return (
            f"Instruction: {unit['style']}\n"
            f"Rewrite rule: {unit['mutation']}\n\n"
            "Apply the rewrite rule to the instruction and give the rewritten "
            "instruction for solving the problem above."
        )
    if kind == 1:
        listed = "\n".join(f"- {member['style']}" for member in units)
        return (
            f"These instructions are in the current population:\n{listed}\n\n"
            "Write one new instruction for solving the problem above that is "
            "different in kind from all of them, not a paraphrase of one."
        )
    if kind == 2 and best_ever is not None:
        return (
            f"The best instruction found so far, scoring {best_ever[0]:.2f}, is:\n"
            f"{best_ever[1]['style']}\n\n"
            "Write a new instruction that continues in the direction that made "
            "it work, and goes further in that direction."
        )
    return (
        f"Rewrite rule: {unit['mutation']}\n\n"
        "This rule is used to rewrite instructions for solving the problem "
        "above. Write a better rewrite rule: one that would produce a more "
        "useful instruction than this one does."
    )


def _mutate_from_catalogue(
    kind: int,
    unit: dict[str, str],
    units: Sequence[dict[str, str]],
    rng: np.random.Generator,
    best_ever: tuple[float, dict[str, str]] | None,
) -> dict[str, str]:
    """The same four families in code, for a variation reply that did not parse."""
    style = unit["style"]
    if kind == 0:
        fresh = THINKING_STYLES[int(rng.integers(len(THINKING_STYLES)))]
        style = f"{fresh} {unit['mutation']}"
    elif kind == 1:
        other = units[int(rng.integers(len(units)))]["style"]
        style = excerpt(f"{style} {other}", 400)
    elif kind == 2 and best_ever is not None:
        style = best_ever[1]["style"]
    else:
        return {
            "style": style,
            "mutation": MUTATION_PROMPTS[int(rng.integers(len(MUTATION_PROMPTS)))],
        }
    return {"style": style.strip(), "mutation": unit["mutation"]}


def evoprompt(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
    *,
    population: int = POPULATION,
    generations: int = GENERATIONS,
) -> BaselineResult:
    """EvoPrompt (Guo et al. 2024), GA variant: roulette selection, crossover, elitism."""
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=budget,
        rng=rng,
        params=generator_params(),
    )
    size = max(1, population)
    instructions = [THINKING_STYLES[i % len(THINKING_STYLES)] for i in range(size)]
    fitness = [0.0] * size
    evaluated = False
    generations_run = 0
    for generation in rounds(ctx):
        if not evaluated:
            produced = sample_candidates(
                ctx,
                [build_prompt(problem, text) for text in instructions],
                iteration=generation,
                meta={"generation": generation},
            )
            if not produced:
                break
            for slot, candidate in enumerate(produced):
                candidate["meta"]["instruction"] = instructions[slot]
                fitness[slot] = candidate["verdict"]
            evaluated = True
            generations_run += 1
            continue
        bred = 0
        for slot in range(size):
            child = _offspring(ctx, instructions, fitness, rng)
            produced = sample_candidates(
                ctx,
                build_prompt(problem, child),
                iteration=generation,
                meta={"generation": generation},
            )
            if not produced:
                break
            bred += 1
            candidate = produced[0]
            candidate["meta"]["instruction"] = child
            score = candidate["verdict"]
            if score >= fitness[slot]:
                instructions[slot], fitness[slot] = child, score
        if not bred:
            break
        generations_run += 1
    return ctx.result(
        arm="evoprompt",
        population=size,
        nominal_generations=generations,
        generations=generations_run,
        variation="LLM crossover and mutation, charged to K; clause splice as fallback",
        best_instruction=instructions[int(np.argmax(fitness))] if fitness else None,
    )


def _offspring(
    ctx: BaselineContext,
    instructions: Sequence[str],
    fitness: Sequence[float],
    rng: np.random.Generator,
) -> str:
    """Roulette-wheel parents, then one LLM evolution call to breed them."""
    weights = np.asarray(fitness, dtype=np.float64) + 0.05
    weights /= weights.sum()
    pair = rng.choice(len(instructions), size=2, replace=True, p=weights)
    a, b = int(pair[0]), int(pair[1])
    body = (
        f"Prompt A: {instructions[a]}\n"
        f"Prompt B: {instructions[b]}\n\n"
        "Cross the two prompts over: take the part of each that is doing the "
        "work and combine them into one instruction. Then mutate the result by "
        "changing one thing about it."
    )
    text = _variation_call(ctx, body, "Instruction")
    if text is not None:
        return text
    return _splice(instructions[a], instructions[b], rng)


def _splice(left_text: str, right_text: str, rng: np.random.Generator) -> str:
    """One-point clause crossover and catalogue mutation, for an unparsed reply."""
    left = _clauses(left_text)
    right = _clauses(right_text)
    cut = int(rng.integers(1, len(left) + 1))
    child = left[:cut] + right[min(cut, len(right) - 1) :]
    if rng.random() < 0.5:
        child[int(rng.integers(len(child)))] = THINKING_STYLES[
            int(rng.integers(len(THINKING_STYLES)))
        ].rstrip(".")
    return ". ".join(part.strip() for part in child if part.strip()) + "."


def _clauses(text: str) -> list[str]:
    parts = [part.strip() for part in text.split(".") if part.strip()]
    return parts or [text.strip()]


def eureka(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
    *,
    generations: int = GENERATIONS,
    samples: int = EUREKA_SAMPLES,
) -> BaselineResult:
    """Eureka (Ma et al. 2024): sample a batch, evaluate, reflect, resample."""
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=budget,
        rng=rng,
        params=generator_params(),
    )
    batch = max(1, samples)
    reflection = ""
    reflected = 0
    generations_run = 0
    best: dict[str, Any] | None = None
    for generation in rounds(ctx):
        prompt = build_prompt(problem, _eureka_guidance(best, reflection))
        produced = sample_candidates(
            ctx, [prompt] * batch, iteration=generation, meta={"generation": generation}
        )
        if not produced:
            break
        generations_run += 1
        top = max(produced, key=lambda c: c["verdict"])
        if best is None or top["verdict"] > best["verdict"]:
            best = top
        feedback = _feedback(produced, generation)
        spoken = _variation_call(ctx, _reflection_body(feedback, top), "Reflection")
        reflection = f"{feedback} {spoken}" if spoken else feedback
        reflected += int(spoken is not None)
    return ctx.result(
        arm="eureka",
        samples_per_generation=batch,
        nominal_generations=generations,
        generations=generations_run,
        reflection=reflection,
        reflections=reflected,
        reflection_source="LLM reflection on execution feedback, charged to K",
    )


def _eureka_guidance(best: dict[str, Any] | None, reflection: str) -> str:
    if best is None:
        return (
            "Write a first solution, and be explicit about the step you are "
            "least sure of."
        )
    return (
        f"Best solution so far (score {best['verdict']:.2f}):\n"
        f"{excerpt(best['text'])}\n\n"
        f"{reflection}\n"
        "Write an improved solution. Keep what the feedback says is working and "
        "change what it says is not."
    )


def _feedback(batch: Sequence[dict[str, Any]], generation: int) -> str:
    """Execution feedback for one generation, read off the verifier."""
    verified = sum(1 for c in batch if c["verified"])
    top = max(batch, key=lambda c: c["verdict"])
    detail = excerpt(str(top["meta"].get("detail") or ""), 200)
    return (
        f"Feedback on generation {generation}: {verified} of {len(batch)} attempts "
        f"passed verification, best score {top['verdict']:.2f}."
        + (f" Verifier: {detail}" if detail else "")
    )


def _reflection_body(feedback: str, top: dict[str, Any]) -> str:
    """Eureka's reward reflection: read the execution feedback, say what to change."""
    return (
        f"{feedback}\n\n"
        f"Best attempt of that generation:\n{excerpt(top['text'])}\n\n"
        "Reflect on this feedback: say which part of the attempt the scores "
        "blame and what the next attempt should do differently."
    )


def universe_of_thoughts(
    problem: Problem,
    backend: Any,
    verifier: Callable[[Problem, str], Any],
    budget: int,
    rng: np.random.Generator,
) -> BaselineResult:
    """Universe of Thoughts (Suzuki et al. 2025), the paper's strongest baseline."""
    ctx = BaselineContext(
        problem=problem,
        backend=backend,
        verifier=verifier,
        budget=budget,
        rng=rng,
        params=generator_params(),
    )
    pool: list[dict[str, Any]] = []
    by_regime: dict[str, int] = {regime: 0 for regime in REGIMES}
    for index in rounds(ctx):
        for regime in REGIMES:
            parents = _draw_parents(pool, regime, rng)
            produced = sample_candidates(
                ctx,
                build_prompt(problem, _regime_guidance(regime, parents)),
                iteration=index,
                meta={
                    "regime": regime,
                    "parents": [p["meta"].get("thought_id") for p in parents],
                },
            )
            if not produced:
                break
            thought = produced[0]
            thought["meta"]["thought_id"] = len(pool)
            judged = ctx.ask(_novelty_prompt(problem, thought["text"], pool))
            thought["meta"]["novelty"] = value_score(judged.text) if judged else 0.5
            thought["meta"]["novelty_judged"] = judged is not None
            by_regime[regime] += 1
            pool.append(thought)
    novelties = [c["meta"]["novelty"] for c in pool]
    return ctx.result(
        arm="uot",
        regimes=list(REGIMES),
        thoughts=len(pool),
        by_regime=by_regime,
        mean_novelty=float(np.mean(novelties)) if novelties else 0.0,
        judge="backbone, charged to K",
    )


def _draw_parents(
    pool: Sequence[dict[str, Any]], regime: str, rng: np.random.Generator
) -> list[dict[str, Any]]:
    """Sample parents with weight 0.5 * quality + 0.5 * novelty, plus a floor."""
    wanted = 2 if regime == "combinatorial" else 1
    if len(pool) < wanted:
        return []
    weights = np.array(
        [
            0.5 * c["verdict"] + 0.5 * float(c["meta"].get("novelty", 0.5)) + 0.05
            for c in pool
        ],
        dtype=np.float64,
    )
    weights /= weights.sum()
    picks = rng.choice(len(pool), size=wanted, replace=False, p=weights)
    return [pool[int(i)] for i in picks]


def _regime_guidance(regime: str, parents: Sequence[dict[str, Any]]) -> str:
    shown = "\n\n".join(f"[thought]\n{excerpt(p['text'])}" for p in parents)
    if regime == "exploratory":
        if not parents:
            return "Solve the problem the way the statement invites you to solve it."
        return (
            f"{shown}\n\nStay inside the space of ideas this thought already "
            "occupies and push it further: take the next step it was going to take, "
            "and take it properly."
        )
    if regime == "combinatorial":
        if len(parents) < 2:
            return (
                "Take two approaches that are normally used for different kinds of "
                "problem and combine them into one solution."
            )
        return (
            f"{shown}\n\nCombine these two lines of thought into one solution that "
            "uses something essential from each. Not a summary of both: one "
            "argument that needs both."
        )
    if not parents:
        return (
            "Solve the problem under a formalism it is not usually posed in, and "
            "say which assumption of the usual framing you dropped."
        )
    return (
        f"{shown}\n\nThe framing of this thought is the thing to change. Name the "
        "assumption it treats as fixed, drop it, and solve the problem in a "
        "different formalism -- then check the answer against the problem as stated."
    )


def _novelty_prompt(problem: Problem, text: str, pool: Sequence[dict[str, Any]]) -> str:
    prior = "\n".join(f"[{i}] {excerpt(c['text'], 200)}" for i, c in enumerate(pool[-6:]))
    body = [
        "Rate how novel the new line of thought is against the ones already tried.",
    ]
    if prior:
        body += ["Already tried:", prior]
    body += [
        "New line of thought:",
        excerpt(text),
        "0 means it restates one of them, 10 means it thinks about the problem in "
        "a genuinely different way. Answer with the integer in \\boxed{}.",
    ]
    return build_prompt(problem, "\n".join(body))
