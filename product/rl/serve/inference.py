"""SageMaker PyTorch inference handler for the merged RL-SCOUT model (greedy, Qwen chat prompt in)."""
import json

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def model_fn(model_dir):
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForCausalLM.from_pretrained(model_dir, torch_dtype=torch.bfloat16).to("cuda").eval()
    return tokenizer, model


def input_fn(body, content_type="application/json"):
    return json.loads(body)


def predict_fn(data, bundle):
    tokenizer, model = bundle
    encoded = tokenizer(data["prompt"], return_tensors="pt", add_special_tokens=False).to("cuda")
    end = tokenizer.convert_tokens_to_ids("<|im_end|>")
    with torch.no_grad():
        out = model.generate(**encoded, max_new_tokens=int(data.get("max_tokens", 160)), do_sample=False,
                             eos_token_id=end, pad_token_id=tokenizer.pad_token_id or end)
    return {"generation": tokenizer.decode(out[0, encoded["input_ids"].shape[1]:], skip_special_tokens=True)}


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction, ensure_ascii=False)
