import json, os, re, shutil, subprocess
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
أعد JSON فقط: {{"title":"عنوان","narration":"نص من 140 إلى 190 كلمة","queries":["five","English","visual","search","phrases"]}}
اجعل المعلومات دقيقة والجمل قصيرة ولا تستخدم Markdown.'''
    api_key = os.environ["GEMINI_API_KEY"]
    response = None
    errors = []
    for version, model in available_models(api_key):
        url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:generateContent"
        response = requests.post(url, params={"key": api_key}, json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=90)
        if response.ok:
            print(f"Gemini model: {model} ({version})")
            break
        errors.append(f"{model}/{version}: HTTP {response.status_code}")
        if response.status_code not in (404, 429):
            response.raise_for_status()
    if response is None or not response.ok:
        raise RuntimeError("All available Gemini models failed: " + "; ".join(errors))
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    match = re.search(r"\{.*\}", text, re.S)
    if not match: raise RuntimeError("Gemini did not return valid JSON")
    return json.loads(match.group(0))

def manual_script(text, topic):
    parts = [p.strip() for p in re.split(r"[.!؟\n]+", text) if p.strip()]
    return {"title":topic, "narration":text, "queries":[topic, *parts[:4]]}

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

def main():
    if OUTPUT.exists(): shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    topic=os.getenv("VIDEO_TOPIC", "حقيقة مذهلة من التاريخ"); supplied=os.getenv("SCRIPT_TEXT", "").strip()
    data=manual_script(supplied, topic) if supplied else generate_script(topic)
    (OUTPUT/"script.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    images=download_images(data["queries"]); voice=OUTPUT/"voice.mp3"; gTTS(data["narration"], lang="ar").save(voice)
    print(f"Created: {render(images, voice)}")

if __name__ == "__main__": main()
