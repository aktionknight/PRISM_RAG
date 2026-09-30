with open('src/slrag/api/ws_server.py', 'r') as f:
    content = f.read()

content = content.replace(
'''            all_candidates = await session.decomposer.decompose(
                prefix=prefix_snap,
                existing_intents=session.state.intent_set,
                ts=ts_snap,
            )''',
'''            all_candidates = await session.decomposer.decompose(
                prefix=prefix_snap,
                existing_intents=session.state.intent_set,
                ts=ts_snap,
                session_state=session.state,
            )'''
)

with open('src/slrag/api/ws_server.py', 'w') as f:
    f.write(content)
