"""bench.latency_llm plumbing against a fake SSE server (the live run needs a local model; audit I-8)."""

import copy
import json

from bench.latency_llm import main, measure, summarise
from slrag.synth.config import load_synth_config
from slrag.synth.generator import OpenAICompatibleClient
from tests.helpers import FakeStreamTransport, pieces, sse

def _claim(intent_id, facet, text, label):
    return {"intent_id": intent_id, "facet": facet, "text": text, "citations": [label]}


REPLIES = [   # one reply per LLM call, in call order: Example 1 V1, Example 2 V1, Example 2 refinement
    [_claim("i1", "venue_capacity", "Venue A holds up to 40 people.", "Doc_12 §2")],
    [_claim("i1", "travel_reimbursement", "Employees are reimbursed for economy airfare and hotel stays of up to "
            "INR 8,000 per night when the claim is filed within 30 days of travel.", "Doc_44 §2"),
     _claim("i1", "travel_reimbursement", "Domestic trips booked in advance through the corporate travel portal "
            "are reimbursed in full without additional approval.", "Doc_44 §3")],
    [_claim("d2_1", "travel_reimbursement", "International trips are reimbursed only when pre-approved by a "
            "department head, with a per-diem allowance of USD 75 per day.", "Doc_44 §7")],
]


class ScriptedTransport(FakeStreamTransport):
    def __init__(self):
        super().__init__([])
        self.replies = iter(REPLIES)

    def __call__(self, url, body, headers, timeout):
        self.lines = sse(pieces(json.dumps({"claims": next(self.replies)}), 8),
                         usage={"prompt_tokens": 900, "completion_tokens": 40})
        return super().__call__(url, body, headers, timeout)


async def test_measure_reports_first_sentence_and_budget_per_turn_type():
    config = copy.deepcopy(load_synth_config())
    config["generator"]["openai_compatible"]["stream"] = True
    transport = ScriptedTransport()

    def client(cfg):
        return OpenAICompatibleClient(cfg, stream_transport=transport)

    rows = await measure(config, 1, client_factory=client)
    summary = summarise(rows)
    assert set(summary) == {"NEW_INTENT", "CONSTRAINT_REFINEMENT"}
    new_intent = summary["NEW_INTENT"]
    assert new_intent["llm_calls_max"] == 1                              # HC-5
    assert new_intent["first_provisional_ms"]["n"] == 2 and new_intent["first_draft_ms"]["n"] == 2


def test_main_refuses_without_a_server(capsys):
    assert main(["--base-url", "http://127.0.0.1:9/v1", "--repeat", "1"]) == 2
    assert "start the local model" in capsys.readouterr().err
