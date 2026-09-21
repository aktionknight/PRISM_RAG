from slrag.core.schemas import SubIntent


# stubs/fake_decomposer.py
def fake_decompose(prefix: str) -> list[SubIntent]:
    return [SubIntent(intent_id="i1", facet="venue_capacity",
                       query_nl="venue capacity for 30 in Pune",
                       search_string="Pune venue capacity 30", novel=True)]
