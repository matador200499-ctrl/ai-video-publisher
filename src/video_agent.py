import json, os, re, shutil, subprocess, time
from pathlib import Path
import requests
from gtts import gTTS

ROOT = Path(__file__).resolve().parent.parent
OUTPUT, ASSETS = ROOT / "output", ROOT / "output" / "images"

def run(*args): subprocess.run(args, check=True)

def available_models(api_key):
    preferred = os.getenv("GEMINI_MODEL", "").strip()
    discovered = []
    for version in ("v1", "v1beta"):
        response = requests.get(
            f"https://generativelanguage.googleapis.com/{version}/models",
            params={"key": api_key, "pageSize": 1000},
            timeout=45,
        )
        if not response.ok:
            continue
        for model in response.json().get("models", []):
            methods = model.get("supportedGenerationMethods", [])
            name = model.get("name", "").removeprefix("models/")
            if "generateContent" in methods and name and not any(word in name for word in ("image", "live", "tts", "embedding")):
                discovered.append((version, name))

    order = [preferred, "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
    ranked = []
    for wanted in order:
        ranked.extend(item for item in discovered if wanted and item[1] == wanted and item not in ranked)
    ranked.extend(item for item in discovered if "flash" in item[1] and item not in ranked)
    ranked.extend(item for item in discovered if item not in ranked)
    if not ranked:
        raise RuntimeError("No Gemini text model is available for this API key. Check the key and Generative Language API access.")
    return ranked

def generate_script(topic):
    prompt = f'''اكتب سكربت فيديو عربي جذاب عن: {topic}
أعد JSON فقط بهذا الشكل:
{{"title":"عنوان","narration":"نص من 100 إلى 120 كلمة","queries":["five","English","visual","search","phrases"],"platforms":{{"facebook":{{"title":"عنوان","description":"وصف","hashtags":["هاشتاج"]}},"instagram":{{"title":"عنوان","description":"وصف","hashtags":["هاشتاج"]}},"tiktok":{{"title":"عنوان","description":"وصف","hashtags":["هاشتاج"]}},"youtube":{{"title":"عنوان","description":"وصف","hashtags":["هاشتاج"]}}}}}}
اجعل المعلومات دقيقة والجمل قصيرة، واضبط النص لفيديو مدته من 45 إلى 60 ثانية، ولا تستخدم Markdown.'''
    api_key = os.environ["GEMINI_API_KEY"]
    response = None
    errors = []
    retryable_statuses = {408, 429, 500, 502, 503, 504}

    # Try several currently available models. Temporary Gemini outages are
    # retried, then the pipeline automatically moves to the next model.
    for version, model in available_models(api_key)[:8]:
        response = None
        url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:generateContent"
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    url,
                    params={"key": api_key},
                    json={"contents":[{"parts":[{"text":prompt}]}]},
                    timeout=90,
                )
            except requests.RequestException as exc:
                errors.append(f"{model}/{version} attempt {attempt}: {type(exc).__name__}")
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                break

            if response.ok:
                print(f"Gemini model: {model} ({version})")
                break

            errors.append(
                f"{model}/{version} attempt {attempt}: HTTP {response.status_code}"
            )
            if response.status_code in retryable_statuses:
                if attempt < 3:
                    wait_seconds = 2 ** attempt
                    print(
                        f"Gemini temporarily unavailable (HTTP {response.status_code}); "
                        f"retrying in {wait_seconds}s..."
                    )
                    time.sleep(wait_seconds)
                    continue
                break
            if response.status_code == 404:
                break
            response.raise_for_status()

        if response is not None and response.ok:
            break

    if response is None or not response.ok:
        raise RuntimeError("All available Gemini models failed: " + "; ".join(errors))
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    match = re.search(r"\{.*\}", text, re.S)
    if not match: raise RuntimeError("Gemini did not return valid JSON")
    return json.loads(match.group(0))

def platform_copy(title):
    common = ["معلومات", "حقائق", "ثقافة", "فيديو"]
    return {
        platform: {"title": title, "description": f"اكتشف القصة الكاملة عن {title}.", "hashtags": common}
        for platform in ("facebook", "instagram", "tiktok", "youtube")
    }

def normalize_data(data, topic):
    data.setdefault("title", topic)
    data.setdefault("queries", [topic])
    generated = platform_copy(data["title"])
    supplied = data.get("platforms") or {}
    for platform, fallback in generated.items():
        item = supplied.get(platform) or {}
        fallback.update({key: value for key, value in item.items() if value})
        supplied[platform] = fallback
    data["platforms"] = supplied
    return data

def manual_script(text, topic):
    parts = [p.strip() for p in re.split(r"[.!؟\n]+", text) if p.strip()]
    return normalize_data({"title":topic, "narration":text, "queries":[topic, *parts[:4]]}, topic)

def download_images(queries):
    ASSETS.mkdir(parents=True, exist_ok=True)
    paths=[]
    for number, query in enumerate(queries[:5], 1):
        r=requests.get("https://api.pexels.com/v1/search", headers={"Authorization":os.environ["PEXELS_API_KEY"]}, params={"query":query,"per_page":1,"orientation":"portrait"}, timeout=45)
        r.raise_for_status(); photos=r.json().get("photos", [])
        if not photos: continue
        image=requests.get(photos[0]["src"]["large2x"], timeout=60); image.raise_for_status()
        path=ASSETS/f"scene-{number:02d}.jpg"; path.write_bytes(image.content); paths.append(path)
    if not paths: raise RuntimeError("Pexels returned no images")
    return paths

def media_duration(path):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(path)], check=True, capture_output=True, text=True)
    return float(r.stdout.strip())

def fit_voice_to_platforms(voice, max_seconds=59.0):
    current = media_duration(voice)
    if current <= max_seconds:
        return voice
    fitted = OUTPUT / "voice-platform-fit.mp3"
    speed = current / max_seconds
    run("ffmpeg", "-y", "-i", str(voice), "-filter:a", f"atempo={speed:.5f}", str(fitted))
    return fitted

def render(images, voice):
    seconds=max(2.0, media_duration(voice)/len(images)); clips=[]
    for index, image in enumerate(images, 1):
        clip=OUTPUT/f"clip-{index:02d}.mp4"; frames=max(1, round(seconds*30))
        vf=f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0008,1.12)':d={frames}:s=1080x1920:fps=30,format=yuv420p"
        run("ffmpeg","-y","-loop","1","-i",str(image),"-vf",vf,"-t",str(seconds),"-an",str(clip)); clips.append(clip)
    listing=OUTPUT/"clips.txt"; listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    silent=OUTPUT/"silent.mp4"; run("ffmpeg","-y","-f","concat","-safe","0","-i",str(listing),"-c","copy",str(silent))
    final=OUTPUT/"final-video.mp4"; run("ffmpeg","-y","-i",str(silent),"-i",str(voice),"-c:v","copy","-c:a","aac","-b:a","192k","-shortest",str(final))
    return final

def publish_to_facebook(video, post):
    page_id = os.environ.get("FACEBOOK_PAGE_ID", "").strip()
    token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
    if not page_id or not token:
        raise RuntimeError("FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN are required")
    hashtags = " ".join(
        tag if str(tag).startswith("#") else f"#{str(tag).replace(' ', '_')}"
        for tag in post.get("hashtags", [])
    )
    description = "\n\n".join(part for part in (post.get("description", ""), hashtags) if part)
    version = os.getenv("FACEBOOK_GRAPH_VERSION", "v26.0")
    url = f"https://graph-video.facebook.com/{version}/{page_id}/videos"
    with video.open("rb") as source:
        response = requests.post(
            url,
            data={"access_token": token, "title": post.get("title", ""), "description": description},
            files={"source": (video.name, source, "video/mp4")},
            timeout=900,
        )
    if not response.ok:
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        raise RuntimeError(f"Facebook upload failed (HTTP {response.status_code}): {message}")
    result = response.json()
    (OUTPUT/"facebook-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Published to Facebook. Video ID: {result.get('id', 'processing')}")
    return result

def main():
    if OUTPUT.exists(): shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    topic=os.getenv("VIDEO_TOPIC", "حقيقة مذهلة من التاريخ"); supplied=os.getenv("SCRIPT_TEXT", "").strip()
    data=manual_script(supplied, topic) if supplied else normalize_data(generate_script(topic), topic)
    (OUTPUT/"script.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT/"platform-posts.json").write_text(json.dumps(data["platforms"], ensure_ascii=False, indent=2), encoding="utf-8")
    images=download_images(data["queries"]); voice=OUTPUT/"voice.mp3"; gTTS(data["narration"], lang="ar").save(voice)
    voice=fit_voice_to_platforms(voice)
    final = render(images, voice)
    print(f"Created: {final}")
    publish_to_facebook(final, data["platforms"]["facebook"])

if __name__ == "__main__": main()
