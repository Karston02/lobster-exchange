"""Shows what's inside a Schwab recording: message counts per stream, the
fields each stream actually sends, and one example message per stream.

Run this on your first recording before writing any parser. The book streams
especially are undocumented, so this is how we learn their real shape.

    python connectors/schwab/inspect_recording.py              # newest recording
    python connectors/schwab/inspect_recording.py data/schwab/<file>.jsonl
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from connect import get_settings

RECORDINGS = get_settings().data_dir / "schwab"


def field_names(value, prefix: str = "", out: Counter | None = None, depth: int = 0) -> Counter:
    """Every key path in a message, e.g. "content[].BIDS[].PRICE", counted."""
    out = out if out is not None else Counter()
    if depth > 6:
        return out
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out[path] += 1
            field_names(item, path, out, depth + 1)
    elif isinstance(value, list):
        for item in value[:5]:
            field_names(item, f"{prefix}[]", out, depth + 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recording", nargs="?", type=Path, default=None)
    parser.add_argument("--example-chars", type=int, default=2500)
    args = parser.parse_args()

    path = args.recording
    if path is None:
        files = sorted(RECORDINGS.glob("*.jsonl"))
        if not files:
            raise SystemExit(f"no recordings in {RECORDINGS}")
        path = files[-1]

    counts: Counter = Counter()
    fields: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, dict] = {}
    first_ns = last_ns = None
    with open(path) as f:
        for line in f:
            record = json.loads(line)
            service = record["service"]
            counts[service] += 1
            field_names(record["msg"], out=fields[service])
            examples.setdefault(service, record["msg"])
            first_ns = first_ns or record["recv_ns"]
            last_ns = record["recv_ns"]

    seconds = (last_ns - first_ns) / 1e9 if first_ns else 0
    print(f"{path}: {sum(counts.values())} messages over {seconds / 60:.1f} minutes")
    for service, n in counts.most_common():
        print(f"\n== {service}: {n} messages ({n / max(seconds, 1):.1f}/s)")
        print("   fields seen:")
        for name, seen in sorted(fields[service].items()):
            print(f"     {name}  ({seen})")
        text = json.dumps(examples[service], indent=2)
        print("   example message:")
        print("     " + text[: args.example_chars].replace("\n", "\n     "))
        if len(text) > args.example_chars:
            print("     ...")


if __name__ == "__main__":
    main()
