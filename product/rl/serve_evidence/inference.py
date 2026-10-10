"""Raw evidence policy generation with verified checkpoint lineage; no silent repair."""
import hashlib
import json
from pathlib import Path


def _file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_fn(model_dir):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    root = Path(model_dir)
    lineage = json.loads((root / "lineage.json").read_text())
    if (lineage.get("schema") != "rl-scout-evidence-lineage-v1" or lineage.get("selectedStage") != "rl"
            or lineage.get("sourceTrainingJob") != "rl-scout-evidence-3b-two-teams-1010-052032"
            or lineage.get("baseRevision") != "aa8e72537993ba99e69dfaafa59ed015b17504d1"
            or not lineage.get("actualRL") or not lineage.get("modelWeights")):
        raise ValueError("Unexpected evidence model lineage")
    for name, expected in lineage["modelWeights"].items():
        if Path(name).name != name or _file_sha(root / name) != expected:
            raise ValueError("Serving weights do not match packaged lineage")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(root, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(root, torch_dtype=torch.bfloat16,
                attn_implementation="sdpa", low_cpu_mem_usage=True, local_files_only=True).to(device).eval()
    return {"tokenizer": tokenizer, "model": model, "device": device, "lineage": lineage}


def input_fn(body, content_type="application/json"):
    if content_type.split(";", 1)[0].strip() != "application/json":
        raise ValueError("application/json required")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    return data


def predict_fn(data, bundle):
    # A health request checks loaded lineage without a generation call.
    if data.get("op") == "health":
        return {"status": "ok", "lineage": bundle["lineage"], "device": bundle["device"]}
    import torch
    tok, model = bundle["tokenizer"], bundle["model"]
    max_tokens = data.get("max_tokens", 256)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 512:
        raise ValueError("max_tokens must be an integer in 1..512")
    if isinstance(data.get("prompt"), str) and data["prompt"]:
        prompt = data["prompt"]
    elif isinstance(data.get("messages"), list) and data["messages"]:
        prompt = tok.apply_chat_template(data["messages"], tokenize=False, add_generation_prompt=True)
    else:
        raise ValueError("Nonempty prompt or messages required")
    if len(prompt) > 60000:
        raise ValueError("Prompt too long")
    encoded = tok(prompt, return_tensors="pt", add_special_tokens=False).to(bundle["device"])
    if encoded["input_ids"].shape[1] + max_tokens > 4096:
        raise ValueError("Context exceeds the frozen 4096 token budget")
    end = tok.convert_tokens_to_ids("<|im_end|>")
    with torch.inference_mode():
        result = model.generate(**encoded, max_new_tokens=max_tokens, do_sample=False,
                  eos_token_id=end, pad_token_id=tok.pad_token_id if tok.pad_token_id is not None else end)
    generation = tok.decode(result[0, encoded["input_ids"].shape[1]:], skip_special_tokens=True)
    return {"generation": generation, "lineage": bundle["lineage"]}


def output_fn(prediction, accept="application/json"):
    return json.dumps(prediction, ensure_ascii=False)
