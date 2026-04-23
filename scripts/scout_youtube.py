#!/usr/bin/env python3
"""
Scout 1: YouTube Intel (Gemini API)
Searches YouTube for recent financial videos mentioning watchlist stocks,
pulls transcripts, and uses Gemini to extract stock mentions and theses.

Uses yt-dlp for reliable YouTube search and youtube-transcript-api for transcripts.

Usage:
    python scripts/scout_youtube.py                    # all watchlist stocks
    python scripts/scout_youtube.py --ticker LITE      # single stock
"""
import os
import re
import json
import subprocess
import sys
import time
import concurrent.futures
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi
from utils import load_env, get_watchlist, save_signals, timestamp, CONFIG_DIR

load_env()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Gemini models to try in order (primary → fallbacks)
# See https://ai.google.dev/gemini-api/docs/models for current list
GEMINI_MODELS = [
    "gemini-2.5-flash",        # stable production model, best price-performance
    "gemini-2.5-flash-lite",   # fastest/cheapest, good fallback
    "gemini-3-flash-preview",  # newest, preview tier
]


def load_channels() -> list[dict]:
    """Load YouTube channel config."""
    path = CONFIG_DIR / "youtube_channels.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["channels"]


def search_youtube_ytdlp(query: str, max_results: int = 5) -> list[dict]:
    """
    Search YouTube using yt-dlp (much more reliable than HTML scraping).
    Returns list of {video_id, title, url}.
    """
    try:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            f"ytsearch{max_results}:{query}",
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--quiet",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                vid = data.get("id", "")
                title = data.get("title", "Unknown")
                if vid:
                    videos.append({
                        "video_id": vid,
                        "title": title,
                        "url": f"https://youtube.com/watch?v={vid}",
                    })
            except json.JSONDecodeError:
                continue

        return videos[:max_results]
    except subprocess.TimeoutExpired:
        print(f"    yt-dlp search timed out for: {query}")
        return []
    except Exception as e:
        print(f"    yt-dlp search error: {e}")
        return []


def search_youtube_multi(ticker: str, company_name: str, max_results: int = 5) -> list[dict]:
    """
    Try multiple search queries to maximize video discovery.
    Returns deduplicated list of videos.
    """
    queries = [
        f"{ticker} stock analysis",
        f"{company_name} stock",
        f"{ticker} earnings",
    ]

    seen = set()
    all_videos = []
    for q in queries:
        print(f"    Searching: \"{q}\"...")
        videos = search_youtube_ytdlp(q, max_results=3)
        for v in videos:
            if v["video_id"] not in seen:
                seen.add(v["video_id"])
                all_videos.append(v)
                print(f"      Found: {v['title'][:60]}")
        if len(all_videos) >= max_results:
            break
        time.sleep(1)

    return all_videos[:max_results]


def get_transcript(video_id: str, timeout: int = 15) -> str | None:
    """Get the transcript for a YouTube video (with timeout guard)."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    def _fetch():
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=["en"])
        return " ".join([entry.text for entry in transcript.snippets])[:15000]

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_fetch)
            return future.result(timeout=timeout)
    except FuturesTimeout:
        print(f"    Transcript timed out after {timeout}s")
        return None
    except Exception as e:
        # Shorten noisy error messages
        err = str(e).split("\n")[0][:120]
        print(f"    Transcript error: {err}")
        return None


GEMINI_CALL_TIMEOUT = 45  # seconds per Gemini API call


def _gemini_with_timeout(client, model_name: str, prompt: str, timeout: int = GEMINI_CALL_TIMEOUT):
    """Wrap genai.generate_content in a timeout since the SDK has no native timeout."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    def _call():
        return client.models.generate_content(
            model=model_name, contents=prompt, config={"temperature": 0}
        )

    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_call)
        return future.result(timeout=timeout)


def analyze_with_gemini(ticker: str, company_name: str, videos_with_transcripts: list[dict]) -> dict:
    """Send video transcripts to Gemini for analysis. Tries multiple models on failure."""
    if not GEMINI_API_KEY:
        return {"error": "No Gemini API key"}

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Build the prompt with all transcripts
    transcript_block = ""
    for v in videos_with_transcripts[:3]:
        transcript_block += f"\n\n--- VIDEO: {v['title']} ---\n{v['transcript'][:5000]}\n"

    prompt = f"""You are a financial analyst extracting stock intelligence from YouTube video transcripts.

TASK: Analyze these video transcripts for any mentions or analysis of {ticker} ({company_name}).

{transcript_block}

Return a JSON object (and ONLY the JSON, no markdown fences) with these fields:
{{
  "mentioned": true/false,
  "sentiment": "bullish" / "bearish" / "neutral",
  "thesis_summary": "1-2 sentence summary of what was said about this stock",
  "key_points": ["point 1", "point 2", "point 3"],
  "price_target": null or a number if mentioned,
  "catalyst_mentioned": null or "description of catalyst",
  "confidence": "high" / "medium" / "low" (based on depth of analysis in the video)
}}

If the stock is NOT mentioned in any transcript, return:
{{
  "mentioned": false,
  "sentiment": "neutral",
  "thesis_summary": "Not discussed in recent videos from monitored channels",
  "key_points": [],
  "price_target": null,
  "catalyst_mentioned": null,
  "confidence": "low"
}}"""

    # Try each model with retries
    last_error = None
    for model_name in GEMINI_MODELS:
        for attempt in range(2):  # 2 attempts per model
            try:
                print(f"    Trying {model_name} (attempt {attempt + 1})...")
                response = _gemini_with_timeout(client, model_name, prompt)
                text = response.text.strip()

                # Clean up markdown code fences
                text = re.sub(r'^```(?:json)?\s*', '', text)
                text = re.sub(r'\s*```$', '', text)

                result = json.loads(text)
                print(f"    ✓ {model_name} succeeded")
                return result

            except json.JSONDecodeError:
                print(f"    [{ticker}] {model_name} returned non-JSON")
                return {
                    "mentioned": False,
                    "sentiment": "neutral",
                    "thesis_summary": f"Gemini analysis inconclusive",
                    "key_points": [],
                    "price_target": None,
                    "catalyst_mentioned": None,
                    "confidence": "low",
                }
            except Exception as e:
                last_error = str(e)
                is_timeout = isinstance(e, (TimeoutError, concurrent.futures.TimeoutError)) or "TimeoutError" in last_error
                is_retryable = "429" in last_error or "503" in last_error or is_timeout
                if is_timeout:
                    print(f"    {model_name}: timed out after {GEMINI_CALL_TIMEOUT}s, trying next model...")
                    break  # Don't retry same model on timeout
                if is_retryable and attempt == 0:
                    print(f"    {model_name}: retryable error, waiting 15s...")
                    time.sleep(15)
                    continue
                elif is_retryable:
                    print(f"    {model_name}: still failing, trying next model...")
                    break
                else:
                    # Non-retryable error (404, auth, etc) — try next model
                    print(f"    {model_name}: {last_error[:80]}")
                    break

    # All models failed
    print(f"  [{ticker}] All Gemini models failed. Last error: {last_error[:100] if last_error else 'unknown'}")
    return {
        "mentioned": False,
        "sentiment": "neutral",
        "thesis_summary": f"Gemini unavailable — all models returned errors",
        "key_points": [],
        "price_target": None,
        "catalyst_mentioned": None,
        "confidence": "low",
    }


def main():
    print("=" * 50)
    print("SCOUT 1: YOUTUBE INTEL (Gemini)")
    print("=" * 50)

    if not GEMINI_API_KEY:
        print("\n  ❌ GEMINI_API_KEY not set!")
        print("  Add your key to .env file")
        return []

    # Support --ticker LITE to test a single stock
    single_ticker = None
    for i, arg in enumerate(sys.argv):
        if arg == "--ticker" and i + 1 < len(sys.argv):
            single_ticker = sys.argv[i + 1].upper()

    watchlist = get_watchlist()
    if single_ticker:
        watchlist = [s for s in watchlist if s["ticker"] == single_ticker]
        if not watchlist:
            print(f"\n  ❌ {single_ticker} not in watchlist!")
            return []

    channels = load_channels()
    channel_names = [c["name"] for c in channels]

    print(f"\n  Monitoring {len(channels)} channels: {', '.join(channel_names[:4])}...")
    print(f"  Scanning for {len(watchlist)} stock(s)")
    print(f"  Gemini models: {' → '.join(GEMINI_MODELS)}")
    print("-" * 50)

    signals = []

    for stock in watchlist:
        ticker = stock["ticker"]
        name = stock["name"]
        print(f"\n  🔍 Searching YouTube for {ticker} ({name})...")

        # Search for recent videos (multiple queries for better coverage)
        videos = search_youtube_multi(ticker, name, max_results=5)
        print(f"  Total unique videos: {len(videos)}")

        if not videos:
            signals.append({
                "ticker": ticker,
                "scout": "YouTube",
                "ai": "Gemini",
                "signal": "neutral",
                "summary": "No recent YouTube videos found for this stock.",
                "timestamp": timestamp(),
                "data": {"videos_analyzed": 0, "gemini_analysis": None},
            })
            continue

        # Try to get transcripts
        videos_with_transcripts = []
        for v in videos[:3]:  # Top 3 videos
            print(f"    Fetching transcript: {v['title'][:55]}...")
            transcript = get_transcript(v["video_id"])
            if transcript:
                v["transcript"] = transcript
                videos_with_transcripts.append(v)
                print(f"    ✓ Got transcript ({len(transcript)} chars)")
            else:
                print(f"    ✗ No transcript")
            time.sleep(0.5)

        if not videos_with_transcripts:
            signals.append({
                "ticker": ticker,
                "scout": "YouTube",
                "ai": "Gemini",
                "signal": "neutral",
                "summary": f"Found {len(videos)} videos but no transcripts available.",
                "timestamp": timestamp(),
                "data": {"videos_found": len(videos), "videos_analyzed": 0},
            })
            continue

        # Analyze with Gemini
        print(f"  🤖 Sending {len(videos_with_transcripts)} transcripts to Gemini...")
        analysis = analyze_with_gemini(ticker, name, videos_with_transcripts)

        # Build signal
        sentiment = analysis.get("sentiment", "neutral")
        thesis = analysis.get("thesis_summary", "No analysis available")
        mentioned = analysis.get("mentioned", False)

        if not mentioned:
            sentiment = "neutral"

        summary_parts = [thesis]
        if analysis.get("price_target"):
            summary_parts.append(f"PT: ${analysis['price_target']}")
        if analysis.get("catalyst_mentioned"):
            summary_parts.append(f"Catalyst: {analysis['catalyst_mentioned']}")
        summary = " | ".join(summary_parts)

        signal_result = {
            "ticker": ticker,
            "scout": "YouTube",
            "ai": "Gemini",
            "signal": sentiment,
            "summary": summary[:300],
            "timestamp": timestamp(),
            "data": {
                "videos_analyzed": len(videos_with_transcripts),
                "videos_found": len(videos),
                "video_titles": [v["title"] for v in videos[:5]],
                "video_urls": [v["url"] for v in videos[:5]],
                "gemini_analysis": analysis,
            },
        }
        signals.append(signal_result)

        emoji = "🟢" if sentiment == "bullish" else ("🔴" if sentiment == "bearish" else "🟡")
        print(f"  {emoji} [{ticker}] Signal: {sentiment}")
        print(f"  [{ticker}] {thesis[:80]}")

        time.sleep(5)  # Rate limit between stocks

    save_signals("youtube", signals)

    print("\n" + "=" * 50)
    print("YOUTUBE INTEL SUMMARY")
    print("=" * 50)
    for s in signals:
        emoji = "🟢" if s["signal"] == "bullish" else ("🔴" if s["signal"] == "bearish" else "🟡")
        print(f"  {emoji} {s['ticker']:6s} | {s['summary'][:70]}")

    return signals


if __name__ == "__main__":
    main()
