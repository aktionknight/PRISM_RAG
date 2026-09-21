from slrag.core.schemas import RetrievedChunk, SubIntent


# stubs/fake_retriever.py
def fake_retrieve(sub_intent: SubIntent) -> list[RetrievedChunk]:
    return [RetrievedChunk(chunk_id="Doc_12#2#0", doc_id="Doc_12",
                            section_id="2", text="Venue A holds up to 40 people.", score=0.9)]
