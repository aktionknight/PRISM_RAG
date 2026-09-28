import re

def patch_synthesize2():
    with open('config/prompts/synthesize.jinja', 'r', encoding='utf-8') as f:
        text = f.read()

    old_rule = "8. Bounded negatives: For capacity or limit-type queries, if the requested value is absent but chunks state other available values, emit a claim stating the available values and noting none are listed for the requested value (e.g. \"Documented capacities are X, Y; none is listed for <requested value>\"). Cite the chunks providing the available values."
    
    new_rule = "8. Bounded negatives: For capacity or limit-type queries, if the requested value is absent but chunks state other available values, emit a claim stating the available values and noting none are listed for the requested value. To pass copy verification, do not output numbers that are not in the chunks (use 'the requested capacity' instead of '50' if 50 is not in the chunks). Cite the chunks providing the available values."
    
    text = text.replace(old_rule, new_rule)

    with open('config/prompts/synthesize.jinja', 'w', encoding='utf-8') as f:
        f.write(text)

patch_synthesize2()
