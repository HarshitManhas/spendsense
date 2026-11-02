import json

from ..schemas import Draft, FIELDS


def parse_prediction(text: str) -> Draft:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate model field: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Nonstandard JSON constant")

    result = json.loads(text, object_pairs_hook=unique_keys, parse_constant=reject_constant)
    if not isinstance(result, dict) or set(result) != set(FIELDS):
        raise ValueError("Model output must contain exactly the five extraction fields")
    return Draft.model_validate(result)
