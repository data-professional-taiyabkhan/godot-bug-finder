"""
Perception: a local CLIP model that answers one question about a frame.

    "Is the agent actually looking at the game?"

CLIP (ViT-B/32) maps an image and a sentence into the same 512-number
space, so we can compare a frame with short descriptions such as "a
screenshot of a video game" or "a screenshot of a code editor" and see
which one it is closest to. That is zero-shot classification: no training,
no labels, no API key, about 80 ms per frame on my laptop's CPU (i5-11300H).

Why it exists: in May the only two "bugs" this system ever flagged were my
own IDE, captured after the game window dropped out, while the Explorer
kept pressing keys into whatever window had focus. Pixel differences
cannot tell "the scene scrolled" from "this is not the game any more".
CLIP can, so the Explorer checks before it acts, and the Inspector uses
the same check to separate harness failures from game bugs.

What it does NOT do: it cannot see fine-grained physics bugs, such as a
character falling through a ledge. That needs a model that reasons about
what happens across frames (a VLM) or access to the game's state.
"""

import os
from functools import lru_cache

import cv2
import numpy as np

import config

# Keep downloaded weights inside the project folder (easy to find and delete).
os.environ.setdefault("HF_HOME", str(config.HF_CACHE_DIR))


# ─────────────────────────────────────────────────────────────────────────
# MODEL (loaded once, on first use)
# ─────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _model():
    import torch
    from transformers import CLIPModel, CLIPProcessor

    model = CLIPModel.from_pretrained(config.CLIP_MODEL).eval()
    processor = CLIPProcessor.from_pretrained(config.CLIP_MODEL)
    return torch, model, processor


def _unit(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


# ─────────────────────────────────────────────────────────────────────────
# EMBEDDINGS
# ─────────────────────────────────────────────────────────────────────────
def embed_images(frames_bgr: list[np.ndarray], batch_size: int = 16) -> np.ndarray:
    """Frames (OpenCV BGR arrays) -> unit-length CLIP image embeddings (N, 512).

    The path is spelled out rather than hidden behind a helper: vision
    encoder -> pooled [CLS] token -> projection into the shared space.
    """
    torch, model, processor = _model()
    out = []
    for i in range(0, len(frames_bgr), batch_size):
        batch = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames_bgr[i:i + batch_size]]
        pixels = processor(images=batch, return_tensors="pt")["pixel_values"]
        with torch.no_grad():
            pooled = model.vision_model(pixel_values=pixels).pooler_output
            out.append(model.visual_projection(pooled).numpy())
    if not out:
        return np.zeros((0, model.config.projection_dim), dtype=np.float32)
    return _unit(np.concatenate(out))


@lru_cache(maxsize=1)
def _prompt_embeddings() -> tuple[np.ndarray, int]:
    """Unit-length embeddings of the game / not-game descriptions in config."""
    torch, model, processor = _model()
    prompts = config.GAME_PROMPTS + config.NOT_GAME_PROMPTS
    tokens = processor(text=prompts, return_tensors="pt", padding=True)
    with torch.no_grad():
        pooled = model.text_model(input_ids=tokens["input_ids"],
                                  attention_mask=tokens["attention_mask"]).pooler_output
        text = model.text_projection(pooled).numpy()
    return _unit(text), len(config.GAME_PROMPTS)


# ─────────────────────────────────────────────────────────────────────────
# THE QUESTION: IS THIS THE GAME?
# ─────────────────────────────────────────────────────────────────────────
def game_probability(image_embs: np.ndarray) -> np.ndarray:
    """P(frame shows the game) for each embedding.

    Cosine similarity to every description, scaled by CLIP's learned
    temperature, softmaxed across all descriptions; the game descriptions'
    probabilities are summed.
    """
    torch, model, _ = _model()
    text, n_game = _prompt_embeddings()
    logits = float(model.logit_scale.exp()) * image_embs @ text.T
    logits -= logits.max(axis=1, keepdims=True)
    probs = np.exp(logits)
    probs /= probs.sum(axis=1, keepdims=True)
    return probs[:, :n_game].sum(axis=1)


def best_description(image_embs: np.ndarray) -> list[str]:
    """The single closest description for each frame (for logs and reports)."""
    text, _ = _prompt_embeddings()
    prompts = config.GAME_PROMPTS + config.NOT_GAME_PROMPTS
    return [prompts[i] for i in np.argmax(image_embs @ text.T, axis=1)]


def is_game(frame_bgr: np.ndarray) -> tuple[bool, float]:
    """One frame -> (looks like the game?, P(game))."""
    p = float(game_probability(embed_images([frame_bgr]))[0])
    return p >= config.GAME_PROB_MIN, p


def warm_up() -> None:
    """Load the model before the clock starts (the first call takes seconds)."""
    is_game(np.zeros((480, 800, 3), dtype=np.uint8))
