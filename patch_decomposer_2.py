with open('src/slrag/decompose/decomposer.py', 'r') as f:
    content = f.read()

replacement = """        while True:
            if session_state is not None:
                if session_state.turn_llm_calls >= 3:
                    logger.warning("Global turn LLM call limit (3) reached.")
                    break
                session_state.turn_llm_calls += 1

            attempts += 1
            if attempts > min(2, self.max_llm_calls):
                break

            llm_response = await self._call_llm(prompt)

            if llm_response and "sub_intents" in llm_response:
                # Removed redundant rewriting
                break
            else:
                prompt += (
                    "\\n\\nError: Output must match the requested JSON format "
                    "containing 'sub_intents'."
                )
"""
import re
content = re.sub(r'        while True:.*?(?=\n        # Build SubIntent objects)', replacement, content, flags=re.DOTALL)

with open('src/slrag/decompose/decomposer.py', 'w') as f:
    f.write(content)
