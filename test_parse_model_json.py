import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from video_agent import parse_model_json

expected = {"title": "عنوان", "platforms": {"facebook": {"title": "عنوان"}}}
assert parse_model_json(json.dumps(expected, ensure_ascii=False)) == expected
assert parse_model_json("Here is the JSON:\n```json\n" + json.dumps(expected) + "\n```\nDone.") == expected
assert parse_model_json(json.dumps(expected) + "\n{" + '"ignored": true}' ) == expected
try:
    parse_model_json("not JSON")
except RuntimeError as exc:
    assert "complete JSON object" in str(exc)
else:
    raise AssertionError("invalid model output should fail clearly")
print("parse_model_json regression tests passed")
