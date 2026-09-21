from slrag.core.schemas import ControllerDecision, TranscriptChunk


# stubs/fake_controller.py
def fake_controller(chunk: TranscriptChunk) -> ControllerDecision:
    # deterministic: fires RETRIEVE on the 2nd and 3rd chunk of the golden example
    return ControllerDecision(t_s=chunk.t_s, decision="RETRIEVE",
                               reason="stub", confidence=0.9)
