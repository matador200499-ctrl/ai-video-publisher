import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONFIG_FILE = ROOT / "config" / "topics.json"
HISTORY_FILE = ROOT / "data" / "topics.json"


def load_json(path):
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def choose_category():
    config = load_json(CONFIG_FILE)
    categories = config.get("categories", [])

    if not categories:
        raise RuntimeError("No categories configured.")

    return random.choice(categories)


def choose_topic():
    config = load_json(CONFIG_FILE)
    history = load_json(HISTORY_FILE)

    used_topics = history.get("used_topics", [])

    category = choose_category()

    # في المرحلة التالية سيتم استبدال هذا الجزء
    # بمحرك بحث + AI لاختيار موضوع حقيقي جديد.
    candidates = [
        f"أسرار مذهلة في {category}",
        f"حقائق لا تعرفها عن {category}",
        f"القصة الكاملة لأغرب أحداث {category}",
        f"أشياء غريبة حدثت في عالم {category}",
        f"أهم الاكتشافات في مجال {category}"
    ]

    available = [
        topic for topic in candidates
        if topic not in used_topics
    ]

    if not available:
        available = candidates

    topic = random.choice(available)

    used_topics.append(topic)

    # نحتفظ بآخر 500 موضوع فقط
    history["used_topics"] = used_topics[-500:]

    save_json(HISTORY_FILE, history)

    return {
        "category": category,
        "topic": topic,
        "duration_minutes": config.get("target_duration_minutes", 15),
        "language": config.get("language", "ar")
    }


if __name__ == "__main__":
    result = choose_topic()

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ))
