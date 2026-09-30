import sys

with open('src/slrag/decompose/decomposer.py', 'r') as f:
    content = f.read()

replacement = """    async def decompose(
        self,
        prefix: str,
        existing_intents: dict,
        ts: float,
        session_state=None,
    ) -> list:"""
import re
content = re.sub(r'async def decompose\(\s*self,\s*prefix: str,\s*existing_intents: dict\[str, SubIntent\],\s*ts: float,\s*\) -> list\[SubIntent\]:', replacement, content)

llm_call_logic = """        llm_response = None
        attempts = 0

        while True:
            if session_state is not None:
                if session_state.turn_llm_calls >= 3:
                    logger.warning("Global turn LLM call limit (3) reached.")
                    break
                session_state.turn_llm_calls += 1

            attempts += 1
            if attempts > min(2, self.max_llm_calls):
                break"""

old_llm_call = """        llm_response = None
        attempts = 0
        max_attempts = min(2, self.max_llm_calls)

        while attempts < max_attempts:
            attempts += 1"""

content = content.replace(old_llm_call, llm_call_logic)

with open('src/slrag/decompose/decomposer.py', 'w') as f:
    f.write(content)
