"""
Independent validation of generated artefacts (Gherkin scenarios and test
suites).

Two signals that do not depend on the generator:
  * static_checks  — deterministic, no LLM (syntax, scenario coverage,
                     selector grounding against the crawled DOM, CI rules).
  * judge          — an LLM reviewer that did not author the artefact; can be
                     pinned to a different provider/model via VALIDATOR_* env.

`fixer` proposes LLM repairs for the findings; `service` combines everything
into a persisted ValidationReport with an explainable score.
"""
