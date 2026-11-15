"""Concise explanatory prose; input evidence and response schemas stay complete."""

# These are prose targets, not schema limits or a filter on retained evidence.
# A response may use more space when a material warning or assumption requires it.
NARRATIVE_STYLE = (
    "Return only the required JSON object. Keep interpretation focused: normally two or three short "
    "sentences, about 60 words, explaining the stage's decision-relevant findings. Do not repeat the "
    "input dictionaries, hashes, numerical tables or every passing check. Preserve all material "
    "warnings, assumptions, anomalies, pending or missing evidence, uncertainty and constraints, "
    "using extra space when needed to retain them. In the assumptions and anomalies lists, include "
    "only supported findings, once each, as brief phrases; use an empty list only when no such "
    "finding is supported. Do not invent or duplicate findings to fill a list. Cite the exact supplied "
    "citation_id values."
)

STRATEGY_STYLE = (
    "Return only the required JSON object. Give each supplied SKU a focused rationale, normally one "
    "or two short sentences and about 40 words, explaining its computed price, tradeoffs and "
    "uncertainty. Do not repeat the input tables or hashes. Preserve every material warning, "
    "assumption and constraint, using extra space when needed. Return exactly the supplied SKU "
    "identifiers and cite the exact supplied citation_id values."
)


def narrative_prompt(task):
    return task + " " + NARRATIVE_STYLE


def strategy_prompt(task):
    return task + " " + STRATEGY_STYLE
