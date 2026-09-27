import asyncio
from slrag.synth.generator import LLMGenerator
from slrag.core.schemas import SubIntent
from slrag.synth.config import load_synth_config

async def main():
    cfg = load_synth_config()
    g = LLMGenerator(cfg)
    intent = SubIntent(intent_id='1', facet='venue_capacity', query_nl='test', search_string='test', novel=True)
    async for draft in g.generate([intent], {'1': []}, constraints={}):
        print(draft)

asyncio.run(main())
