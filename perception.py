"""Is the Explorer looking at the game? A zero-shot CLIP check.

CLIP (ViT-B/32) puts images and short captions in the same embedding space,
so a frame can be compared with "a screenshot of a video game", "a screenshot
of a code editor" and so on; the closest captions win. No training, no API
key, about 80 ms a frame on a laptop CPU.

It looks at the whole frame, so it can tell the game from an IDE, but not a
normal jump from falling through a ledge.
"""

import os
from functools import lru_cache

import cv2
import numpy as np

import config

os.environ.setdefault("HF_HOME", str(config.HF_CACHE_DIR))  # keep the weights in the project


@lru_cache(maxsize=1)
def _load():
    import torch
    from transformers import CLIPModel, CLIPProcessor

    model = CLIPModel.from_pretrained(config.CLIP_MODEL).eval()
    processor = CLIPProcessor.from_pretrained(config.CLIP_MODEL)
    return torch, model, processor


def _normalise(x):
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def embed_images(frames, batch_size=16):
    """BGR frames -> unit-length CLIP image embeddings, shape (n, 512)."""
    torch, model, processor = _load()
    chunks = []
    for i in range(0, len(frames), batch_size):
        rgb = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames[i:i + batch_size]]
        pixels = processor(images=rgb, return_tensors="pt")["pixel_values"]
        with torch.no_grad():
            # get_image_features() stopped returning a plain tensor in
            # transformers 5, so do its two steps here: pool, then project.
            pooled = model.vision_model(pixel_values=pixels).pooler_output
            chunks.append(model.visual_projection(pooled).numpy())
    if not chunks:
        return np.zeros((0, model.config.projection_dim), dtype=np.float32)
    return _normalise(np.concatenate(chunks))


@lru_cache(maxsize=1)
def _caption_embeddings():
    torch, model, processor = _load()
    tokens = processor(text=config.GAME_PROMPTS + config.NOT_GAME_PROMPTS,
                       return_tensors="pt", padding=True)
    with torch.no_grad():
        pooled = model.text_model(input_ids=tokens["input_ids"],
                                  attention_mask=tokens["attention_mask"]).pooler_output
        text = model.text_projection(pooled).numpy()
    return _normalise(text)


def game_probability(image_embs):
    """P(game) per frame: softmax over all captions, summed over the game ones."""
    _, model, _ = _load()
    scale = model.logit_scale.detach().exp().item()  # CLIP's learned temperature
    logits = scale * image_embs @ _caption_embeddings().T
    logits -= logits.max(axis=1, keepdims=True)
    probs = np.exp(logits)
    probs /= probs.sum(axis=1, keepdims=True)
    return probs[:, :len(config.GAME_PROMPTS)].sum(axis=1)


def best_description(image_embs):
    captions = config.GAME_PROMPTS + config.NOT_GAME_PROMPTS
    return [captions[i] for i in np.argmax(image_embs @ _caption_embeddings().T, axis=1)]


def is_game(frame):
    p = float(game_probability(embed_images([frame]))[0])
    return p >= config.GAME_PROB_MIN, p


def warm_up():
    # The first call loads the model, which takes a few seconds.
    is_game(np.zeros((480, 800, 3), dtype=np.uint8))
