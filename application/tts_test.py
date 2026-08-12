"""Quick TTS smoke test.

    python tts_test.py "Текст для проверки"
    python tts_test.py --provider sapi "Текст"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import load_config
from app.tts import TtsError, list_sapi_voices, speak_text


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?", default="Проверка чтения VoiceService.")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--voices", action="store_true")
    args = parser.parse_args(argv)

    if args.voices:
        for voice in list_sapi_voices():
            print(voice)
        return 0

    cfg = load_config()
    if args.provider:
        cfg["tts_provider"] = args.provider
    try:
        speak_text(args.text, cfg)
    except TtsError as e:
        print(f"TTS error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
