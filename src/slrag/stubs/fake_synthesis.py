from slrag.core.schemas import AnswerOutput


# stubs/fake_synthesis.py
def fake_synthesize(claims) -> AnswerOutput:
    return AnswerOutput(retrieval_events=[], sub_queries=["..."],
                         answer="Stub answer.", citations=["Doc_12 §2"],
                         uncertainty="", session_id="s1", turn_id=1, answer_version=1)
