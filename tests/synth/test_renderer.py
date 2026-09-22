import ast
import importlib.util
from pathlib import Path

import pytest

from slrag.core.schemas import AnswerOutput
from slrag.synth import renderer
from slrag.synth.claims import ClaimGraph
from slrag.synth.renderer import (
    PresentationRequest,
    answer_citations,
    build_answer_output,
    build_extensions,
    parse_presentation_request,
    render_claims,
    render_output_json,
    render_presentation,
)
from slrag.synth.types import PresentationInvariantError
from tests.helpers import load_corpus, scenario_turns, turn_decisions

EX1_CLAIMS = [
    ("venue_capacity", "Doc_12 §2", [
        "Venue A holds up to 40 people.",
        "In classroom layout Venue A seats 30 attendees.",
        "Venue B seats up to 60 people and includes a breakout room.",
    ]),
    ("cancellation_terms", "Doc_31 §4", [
        "Cancellations made more than 14 days before the event receive a full refund.",
        "Cancellations made within 14 days of the event forfeit the 25% booking deposit.",
    ]),
    ("catering_options", "Doc_09 §1", [
        "Venue B offers on-site catering for groups of up to 80 guests.",
        "External caterers must be registered with the venue at least 7 days before the event.",
    ]),
]
FORBIDDEN = ("slrag.retrieve", "slrag.decompose", "slrag.controller", "slrag.stubs", "slrag.ingest")


def _graph(rows=EX1_CLAIMS):
    graph = ClaimGraph("sess_render")
    graph.register_evidence(load_corpus().values())
    with graph.revise() as rev:
        for facet, label, texts in rows:
            for text in texts:
                rev.add(facet=facet, text=text, citations=[label])
    return graph


def test_prose_groups_by_facet_in_first_appearance_order_with_markers():
    graph = ClaimGraph("s")
    graph.register_evidence(load_corpus().values())
    with graph.revise() as rev:
        rev.add(facet="venue_capacity", text="Venue A holds up to 40 people.", citations=["Doc_12 §2"])
        rev.add(facet="cancellation_terms", text="Late cancellations forfeit the deposit.", citations=["Doc_31 §4"])
        rev.add(facet="venue_capacity", text="Venue B costs more.", citations=["Doc_12 §2", "Doc_12 §3"])
    assert render_claims(graph.active()) == (
        "Venue A holds up to 40 people. [Doc_12 §2] "
        "Venue B costs more. [Doc_12 §2; Doc_12 §3] "
        "Late cancellations forfeit the deposit. [Doc_31 §4]"
    )
    assert answer_citations(graph.active()) == ["Doc_12 §2", "Doc_31 §4", "Doc_12 §3"]


@pytest.mark.parametrize("utterance, expected", [
    ("Can you repeat that in two bullets?", PresentationRequest("bullets", 2, "presentation_restructure")),
    ("Give me that as a numbered list of 3", PresentationRequest("numbered", 3, "presentation_restructure")),
    ("Bullet it for me", PresentationRequest("bullets", None, "presentation_restructure")),
    ("Can you shorten that?", PresentationRequest("short", None, "presentation_restructure")),
    ("Please rephrase your last answer", PresentationRequest("prose", None, "presentation_restructure")),
    ("Translate that into Hindi", PresentationRequest("prose", None, "translation")),
    ("Say it in a friendlier tone", PresentationRequest("prose", None, "tone_change")),
])
def test_parse_presentation_request(utterance, expected):
    assert parse_presentation_request(utterance) == expected


def test_example3_repeat_in_two_bullets_reuses_claims_only():
    turn = scenario_turns("example3_presentation")[-1]
    graph = _graph()
    prior = graph.citations()
    request = parse_presentation_request(turn["utterance"])
    assert request == PresentationRequest("bullets", 2, "presentation_restructure")
    assert request.reason == turn["expected"]["suppression_reason"]

    text, citations = render_presentation(graph, request, prior_citations=prior)
    lines = text.splitlines()
    assert len(lines) == turn["expected"]["bullet_count"] == 2
    assert all(line.startswith("- ") for line in lines)
    assert set(citations) <= set(prior) and citations == prior
    assert all(text.count(claim.text) == 1 for claim in graph.active())
    assert "Venue A holds" in lines[0] and "Cancellations" not in lines[0]       # facets never split
    assert "Cancellations" in lines[1] and "catering" in lines[1]
    assert graph.version == turn["expected"]["answer_version"] == 1           # graph untouched


def test_presentation_invariant_raises_when_prior_misses_a_label():
    graph = _graph()
    with pytest.raises(PresentationInvariantError, match="Doc_09 §1"):
        render_presentation(graph, PresentationRequest("prose", None, "presentation_restructure"),
                            prior_citations=["Doc_12 §2", "Doc_31 §4"])


@pytest.mark.parametrize("bullets, sizes", [
    (None, [3, 2, 2]),        # one bullet per facet
    (1, [7]),
    (2, [3, 4]),
    (3, [3, 2, 2]),
    (5, [1, 1, 1, 2, 2]),     # more bullets than facets: split the largest groups
    (20, [1] * 7),            # capped at #claims
])
def test_bullet_distribution(bullets, sizes):
    text = render_claims(_graph().active(), style="bullets", bullets=bullets)
    lines = text.splitlines()
    assert [line.count("[Doc_") for line in lines] == sizes
    assert all(line.startswith("- ") for line in lines)


def test_numbered_and_short_styles():
    claims = _graph().active()
    numbered = render_claims(claims, style="numbered", bullets=3).splitlines()
    assert [line[:3] for line in numbered] == ["1. ", "2. ", "3. "]
    assert render_claims(claims, style="short") == (
        "Venue A holds up to 40 people. [Doc_12 §2] "
        "Cancellations made more than 14 days before the event receive a full refund. [Doc_31 §4] "
        "Venue B offers on-site catering for groups of up to 80 guests. [Doc_09 §1]"
    )
    with pytest.raises(ValueError):
        render_claims(claims, style="haiku")
    with pytest.raises(ValueError):
        render_claims(claims, style="bullets", bullets=0)
    assert render_claims([], style="bullets", bullets=2) == ""


def _output(**overrides):
    turn = scenario_turns("example1_multi_intent")[0]
    kwargs = dict(
        session_id="sess_a91c", turn_id=1, answer_version=1, answer="A.",
        citations=turn["expected"]["citations"], uncertainty="U.",
        sub_queries=turn["expected"]["sub_queries"], retrieval_events=turn["retrieval_events"],
    )
    kwargs.update(overrides)
    return build_answer_output(**kwargs)


def test_build_answer_output_validates_retrieval_events():
    output = _output()
    assert isinstance(output, AnswerOutput) and type(output) is AnswerOutput
    assert [e["trigger"] for e in output.retrieval_events] == ["provisional", "multi_intent", "multi_intent"]
    good = {"timestamp_s": 0.8, "query": "q", "trigger": "provisional"}
    for bad in (
        {**good, "trigger": "speculative"},
        {**good, "extra": 1},
        {"timestamp_s": 0.8, "query": "q"},
        {**good, "timestamp_s": "0.8"},
        {**good, "query": ""},
        ("timestamp_s", "query", "trigger"),
    ):
        with pytest.raises(ValueError):
            _output(retrieval_events=[bad])


def test_extensions_and_output_json_key_order():
    turn = scenario_turns("example1_multi_intent")[0]
    graph = _graph()
    ext = build_extensions(
        retrieval_required=True, suppression_reason=None, controller_decisions=turn_decisions(turn),
        graph=graph, lineage=graph.latest_lineage(), telemetry={"cost_usd": 0.0},
    )
    assert ext["controller_decisions"][1] == {
        "timestamp_s": 0.8, "decision": "RETRIEVE", "reason": "corpus_discriminative", "confidence": 0.78,
    }
    assert ext["claims"] == graph.to_output()
    assert ext["version_lineage"]["to"] == 1 and len(ext["version_lineage"]["added"]) == 7

    merged = render_output_json(_output(), ext)
    assert list(merged) == [
        "retrieval_events", "sub_queries", "answer", "citations", "uncertainty",
        "session_id", "turn_id", "answer_version",
        "retrieval_required", "suppression_reason", "controller_decisions", "claims",
        "version_lineage", "telemetry",
    ]
    with pytest.raises(ValueError):
        render_output_json(_output(), {"answer": "overridden"})


def _slrag_imports(path: Path, module: str) -> list[tuple[str, list[str]]]:
    """(module, imported names) for every import in ``path``, relative imports resolved."""
    package = module.rsplit(".", 1)[0]
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(alias.name, []) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                target = f"{base}.{target}" if target else base
            found.append((target, [alias.name for alias in node.names]))
    return found


def test_renderer_cannot_reach_retrieval():
    """Presentation path: retrieval is structurally unreachable (A_FINAL_ARCHITECTURE §4.3)."""
    direct = _slrag_imports(Path(renderer.__file__), renderer.__name__)
    names = [name for _, imported in direct for name in imported]
    assert not [n for n in names if "retriev" in n.lower() or "pool" in n.lower()]

    seen, stack = set(), [renderer.__name__]
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        origin = importlib.util.find_spec(module).origin
        for target, _ in _slrag_imports(Path(origin), module):
            if target.startswith("slrag.") and target not in seen:
                stack.append(target)
    assert not [m for m in seen if m.startswith(FORBIDDEN)], sorted(seen)
    assert "slrag.synth.claims" in seen          # sanity: the walk actually followed imports
