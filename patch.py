import io

with open('config/prompts/decompose.jinja', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    '5. Generate an optimised search_string for each sub-query (keywords, not a sentence).',
    '5. Generate an optimised search_string for each sub-query (keywords, not a sentence).\n6. Emit a dictionary of extracted slots for constraints (e.g., {"attendees": 30}).\n7. Output the user\'s FINAL intended intent set for the full prefix. If an intent revises or corrects a previous intent from the "Already Identified Intents" list, include the ID of the old intent in the `supersedes` list.'
)

text = text.replace(
    '{% for intent in existing_intents %}\n- [{{ intent.facet }}] {{ intent.query_nl }}\n{% endfor %}',
    '{% for intent in existing_intents %}\n- [{{ intent.facet }}] {{ intent.query_nl }} (ID: {{ intent.intent_id }})\n{% endfor %}'
)

text = text.replace(
    '      "search_string": "<optimised search keywords>",\n      "novel": true',
    '      "search_string": "<optimised search keywords>",\n      "novel": true,\n      "slots": {"key": "value"},\n      "supersedes": ["<intent_id>"]'
)

with open('config/prompts/decompose.jinja', 'w', encoding='utf-8') as f:
    f.write(text)
