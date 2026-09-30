with open('src/slrag/controller/cascade.py', 'r') as f:
    content = f.read()

import re
replacement = """async def _do_tiebreak(prefix: str, session: ControllerState):
    if hasattr(session, 'session') and hasattr(session.session, 'turn_llm_calls'):
        if session.session.turn_llm_calls >= 3:
            logger.debug("Tie-break skipped due to turn_llm_calls >= 3")
            return
        session.session.turn_llm_calls += 1
"""
content = re.sub(r'async def _do_tiebreak\(prefix: str, session: ControllerState\):', replacement, content)

with open('src/slrag/controller/cascade.py', 'w') as f:
    f.write(content)
