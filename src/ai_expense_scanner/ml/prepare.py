import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from datasets import Image, load_from_disk

from .data import adapt, serialize_target


def prepare(root: Path, output: Path, seed: int = 42):
    output.mkdir(parents=True, exist_ok=True)
    records = {key: [] for key in ("train", "validation", "test")}
    report = {"seed": seed, "adapter_version": 1, "sources": {}, "excluded": []}
    for source in ("cord", "sroie"):
        ds = load_from_disk(str(root / source))
        report["sources"][source] = {"counts": {k: len(v) for k, v in ds.items()}, "fingerprints": {k: v._fingerprint for k, v in ds.items()}}
        for split, dataset in ds.items():
            # Encoded byte hashes without expanding all images or writing duplicate copies.
            dataset = dataset.cast_column("image", Image(decode=False))
            for index, row in enumerate(dataset):
                parsed = adapt(row, source)
                dest = split
                if source == "sroie" and split == "train":
                    group = (parsed["targets"]["merchant"] or row["key"]).casefold()
                    fraction = int(hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()[:8], 16) / 2**32
                    dest = "validation" if fraction < .15 else "train"
                image = row["image"]
                content = image["bytes"] if image["bytes"] is not None else Path(image["path"]).read_bytes()
                records[dest].append({"source": source, "split": split, "index": index,
                    "id": f"{source}:{split}:{index}", "sha256": hashlib.sha256(content).hexdigest(), **parsed})
    # Evaluation takes precedence: remove training/validation duplicates, never move test images into training.
    seen = set()
    for split in ("test", "validation", "train"):
        kept = []
        for record in records[split]:
            if record["sha256"] in seen and split != "test":
                report["excluded"].append({"id": record["id"], "reason": "duplicate_image"})
                continue
            seen.add(record["sha256"])
            kept.append(record)
        records[split] = kept
        with (output / f"{split}.jsonl").open("w", encoding="utf-8") as handle:
            for record in kept:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    report["prepared_counts"] = {key: len(value) for key, value in records.items()}
    report["training_label_coverage"] = dict(Counter(f"{r['source']}.{k}.{state}" for r in records["train"] for k, state in r["label_states"].items()))
    report["limitations"] = ["Byte-hash deduplication only; near-duplicate/layout audit pending", "Ambiguous dates and CORD multi-section tax excluded from supervision", "Currency requires new verified labels", "Images not all decoded for corruption audit"]
    (output / "audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    from .vocabulary import Vocabulary
    vocab = Vocabulary.build([serialize_target(r["targets"], r["label_states"])[0] for r in records["train"]])
    (output / "vocabulary.json").write_text(json.dumps(vocab.characters, ensure_ascii=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Prepare existing CORD/SROIE snapshots without downloading")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("data/manifests"))
    args = parser.parse_args()
    report = prepare(args.data, args.output)
    print(json.dumps({"counts": report["prepared_counts"], "excluded": len(report["excluded"]), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
