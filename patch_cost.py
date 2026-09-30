with open('src/slrag/telemetry/cost.py', 'r') as f:
    content = f.read()

replacement = """def make_cost_accumulator(config: dict | None = None) -> CostAccumulator:
    \"\"\"Create a cost accumulator with rates from config.\"\"\"
    pricing = config or load_pricing()
    models = pricing.get("models", {})
    rates = {}
    if models:
        # F12: Fix nested config loading by taking the first model's rates or matching
        rates = next(iter(models.values()))
    acc = CostAccumulator()
    acc._rates = rates
    return acc"""
import re
content = re.sub(r'def make_cost_accumulator.*?return acc', replacement, content, flags=re.DOTALL)

# And fix _compute_cost
content = content.replace('self._rates.get("prompt_per_1k", 0.0)', 'self._rates.get("prompt_per_1k_tokens", 0.0)')
content = content.replace('self._rates.get("completion_per_1k", 0.0)', 'self._rates.get("completion_per_1k_tokens", 0.0)')

with open('src/slrag/telemetry/cost.py', 'w') as f:
    f.write(content)
