#!/usr/bin/env python3
"""Bake the Component 4 NLI cross-encoder into the build (audit I-4, gate G1).

``CrossEncoderNLIScorer`` never downloads weights at runtime: it loads them from
``verifier.cross_encoder.model_path``. This script is the one place that fetches
them, at build time (``make setup-nli`` / the Docker build), and then checks that
the model's own label order matches ``verifier.cross_encoder.labels`` so the
entailment column can never be read from the wrong logit.

    python scripts/bake_nli_model.py                       # -> models/nli-deberta-v3-small
    python scripts/bake_nli_model.py --check               # verify an existing bake only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from slrag.synth.config import load_synth_config, resolve_path  # noqa: E402

DEFAULT_REPO_ID = "cross-encoder/nli-deberta-v3-small"


def check(path: Path, labels: list[str]) -> None:
    config_file = path / "config.json"
    if not config_file.exists():
        raise SystemExit(f"no model at {path} (missing config.json); run without --check to bake it")
    id2label = json.loads(config_file.read_text(encoding="utf-8")).get("id2label", {})
    model_labels = [str(id2label[str(i)]).lower() for i in range(len(id2label))]
    if model_labels != labels:
        raise SystemExit(
            f"label order mismatch: model {model_labels} vs verifier.cross_encoder.labels {labels}; "
            "fix config/synth.yaml before enabling entailment_backend: cross_encoder"
        )
    print(f"ok: {path} labels {model_labels}")


def bake_spacy(*, check_only: bool, package: str = "en_core_web_sm") -> None:
    """Copy the spaCy pipeline to ``verifier.spacy.model_path`` so runtime loads it from disk."""
    import spacy

    path = resolve_path(load_synth_config()["verifier"].get("spacy", {}).get("model_path", f"models/{package}"))
    if not check_only:
        try:
            nlp = spacy.load(package)
        except OSError:
            from spacy.cli import download

            download(package)
            nlp = spacy.load(package)
        nlp.to_disk(path)
    ents = [(e.text, e.label_) for e in spacy.load(str(path))("Marriott holds up to 40 people.").ents]
    print(f"ok: {path} -> {ents}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help="Hugging Face model id")
    parser.add_argument("--revision", default=None, help="pin a model revision (commit hash) for reproducible builds")
    parser.add_argument("--check", action="store_true", help="only verify an existing bake")
    parser.add_argument("--spacy", action="store_true",
                        help="also bake the spaCy NER model for verifier.entity_backend: spacy (W-6)")
    args = parser.parse_args()
    if args.spacy:
        bake_spacy(check_only=args.check)

    cfg = load_synth_config().get("verifier", {}).get("cross_encoder", {})
    path = resolve_path(cfg.get("model_path", "models/nli-deberta-v3-small"))
    labels = [str(label).lower() for label in cfg.get("labels", ("contradiction", "entailment", "neutral"))]
    if not args.check:
        from huggingface_hub import snapshot_download   # ships with sentence-transformers ([nli] extra)

        path.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=args.repo_id,
            revision=args.revision,
            local_dir=str(path),
            allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt"],
        )
    check(path, labels)


if __name__ == "__main__":
    main()
