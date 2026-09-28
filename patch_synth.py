import re

def patch_synthesize():
    with open('config/prompts/synthesize.jinja', 'r', encoding='utf-8') as f:
        text = f.read()

    old_rule_7 = "7. Where session constraints are given, prefer the facts that apply under them, but state only what the chunks say."
    new_rules = "7. Where session constraints are given, prefer the facts that apply under them, but state only what the chunks say.\n8. Bounded negatives: For capacity or limit-type queries, if the requested value is absent but chunks state other available values, emit a claim stating the available values and noting none are listed for the requested value (e.g. \"Documented capacities are X, Y; none is listed for <requested value>\"). Cite the chunks providing the available values."
    
    text = text.replace(old_rule_7, new_rules)

    with open('config/prompts/synthesize.jinja', 'w', encoding='utf-8') as f:
        f.write(text)

patch_synthesize()
