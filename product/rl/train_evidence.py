#!/usr/bin/env python3
"""Frozen two-team evidence tasks: verified SFT, then on-policy grouped RL.

Only assistant tokens carry loss. Tool responses come from Environment.execute,
and rewards use that environment's private trace. No numbers or oracle fields are
inserted into the initial policy prompt. --dry-run needs only the standard library.
"""
import argparse
from collections import Counter, defaultdict
import gc
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import time

HERE = Path(__file__).resolve().parent
SPLITS = ("train", "val", "test")
TRAIN_WEIGHTS = {"joint_three_layer": .35, "basic_advanced": .20, "basic_lookup": .075,
                 "advanced_lookup": .075, "depth_lookup": .15, "missing_family": .05,
                 "event_boundary": .04, "as_of_boundary": .035, "causal_boundary": .025}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def balanced_rows(rows, count, seed, replacement=False):
    """Category quotas; source IDs stay within their split, repeats are explicit."""
    buckets = defaultdict(list)
    for row in rows:
        buckets[row.get("category", "unknown")].append(row)
    if not replacement:
        count = min(count, len(rows))
    if count == 0:
        return []
    weights = {k: TRAIN_WEIGHTS.get(k, .01) for k in buckets}
    norm = sum(weights.values())
    target = {k: count * v / norm for k, v in weights.items()}
    assigned = {k: 0 for k in buckets}
    if "joint_three_layer" in buckets:
        quota = math.ceil(count * .35)
        assigned["joint_three_layer"] = min(quota, len(buckets["joint_three_layer"])) if not replacement else quota
    if count >= len(buckets):
        for key in sorted(buckets, key=lambda k: (-weights[k], k)):
            if sum(assigned.values()) < count and not assigned[key]:
                assigned[key] = 1
    while sum(assigned.values()) < count:
        candidates = [k for k in buckets if replacement or assigned[k] < len(buckets[k])]
        key = max(candidates, key=lambda k: (target[k] - assigned[k], k))
        assigned[key] += 1
    rng, chosen = random.Random(seed), []
    for key in sorted(buckets):
        bucket = list(buckets[key])
        rng.shuffle(bucket)
        chosen.extend(bucket[:assigned[key]])
        if assigned[key] > len(bucket):
            chosen.extend(rng.choices(bucket, k=assigned[key] - len(bucket)))
    rng.shuffle(chosen)
    return chosen


def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    p.add_argument("--store", default=str(HERE / "data/evidence/store.json"))
    p.add_argument("--tasks", default=str(HERE / "data/evidence/tasks.jsonl"))
    p.add_argument("--out", default=os.environ.get("RL_OUT", "/opt/ml/checkpoints"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--seed", type=int, default=31)
    p.add_argument("--sft-epochs", type=int, default=1)
    p.add_argument("--sft-max-tasks", type=int, default=320)
    p.add_argument("--sft-lr", type=float, default=1e-4)
    p.add_argument("--accumulation", type=int, default=4)
    p.add_argument("--steps", type=int, default=40)
    p.add_argument("--prompts-per-step", type=int, default=2)
    p.add_argument("--group", type=int, default=4)
    p.add_argument("--lr", type=float, default=8e-6)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--max-new", type=int, default=256)
    p.add_argument("--max-sequence", type=int, default=4096)
    p.add_argument("--max-turns", type=int, default=3)
    p.add_argument("--generation-batch", type=int, default=2)
    p.add_argument("--micro-batch", type=int, default=1)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--eval-n", type=int, default=24, help="fixed count per held-out split; 0 means all")
    p.add_argument("--min-sft-valid", type=float, default=0.95, help="held-out JSON/schema validity required before RL")
    p.add_argument("--time-budget", type=int, default=3000, help="training + evaluations after model load, seconds")
    p.add_argument("--final-reserve", type=int, default=600)
    p.add_argument("--merge", type=int, choices=(0, 1), default=0, help="CPU merge selected adapter after evaluation")
    a = p.parse_args(argv)
    for name in ("sft_epochs", "sft_max_tasks", "accumulation", "prompts_per_step", "group",
                 "generation_batch", "micro_batch", "max_new", "max_sequence", "max_turns", "time_budget"):
        if getattr(a, name) < 1:
            p.error(name + " must be positive")
    if a.group < 2 or a.steps < 0 or a.eval_n < 0 or not 0 <= a.min_sft_valid <= 1:
        p.error("invalid RL group, steps, evaluation count or validity threshold")
    if not 0 < a.final_reserve < a.time_budget:
        p.error("final-reserve must fit within time-budget")
    if a.micro_batch > 2 or a.generation_batch > 4:
        p.error("this bounded-memory experiment permits micro-batch <= 2 and generation-batch <= 4")
    if a.temperature != 1.0:
        p.error("single-update policy gradient requires temperature=1.0 for matching sampling/log probabilities")
    if "Qwen2.5-" not in a.model:
        p.error("this runner's exact chat continuation is restricted to Qwen2.5")
    return a


def load_inputs(a):
    env = importlib.import_module("evidence_env")
    store = json.loads(Path(a.store).read_text())
    if store.get("schema") != "rl-scout-evidence-store-v1":
        raise ValueError("Unexpected evidence store schema")
    task_path = Path(a.tasks)
    tasks = ([json.loads(line) for line in task_path.read_text().splitlines() if line.strip()]
             if task_path.is_file() else env.make_tasks(store))
    ids = [str(t["id"]) for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate frozen task ID")
    if {t.get("split") for t in tasks} != set(SPLITS):
        raise ValueError("Frozen train/val/test splits are all required")
    by_split = {split: sorted([t for t in tasks if t["split"] == split], key=lambda t: str(t["id"]))
                for split in SPLITS}
    evaluation = {}
    for split in ("val", "test"):
        rows = by_split[split]
        # The same IDs are used before training, after SFT and after RL.
        if not a.eval_n or a.eval_n >= len(rows):
            evaluation[split] = rows
            continue
        evaluation[split] = sorted(balanced_rows(rows, a.eval_n, a.seed), key=lambda t: str(t["id"]))
    manifest = {"schema": "rl-scout-evidence-training-input-v1", "storeSha256": digest(store),
                "tasksSha256": digest(tasks), "counts": {k: len(v) for k, v in by_split.items()},
                "splitIds": {k: [t["id"] for t in v] for k, v in by_split.items()},
                "evaluationIds": {k: [t["id"] for t in v] for k, v in evaluation.items()},
                "evaluationCategories": {k: dict(Counter(t.get("category", "unknown") for t in v))
                                         for k, v in evaluation.items()},
                "evaluationScope": "retrieval_and_structured_evidence_not_visual_understanding",
                "heldOutUse": "val gates RL/selects stage; test reports frozen pre/SFT/RL comparison only"}
    return env, store, tasks, by_split, evaluation, manifest


def teacher_trace(env, store, task):
    executor = env.Environment(task, store)
    turns, final = [], None
    for action in env.teacher_actions(task, store):
        text = action if isinstance(action, str) else canonical(action)
        kind, payload, invalid = env.parse_action(text)
        if invalid:
            raise ValueError("Invalid teacher action: " + str(task["id"]))
        if kind == "tools" and final is None:
            results = [executor.execute(tool) for tool in payload]
            turns.append({"assistant": text, "toolResults": results})
        elif kind == "answer" and final is None:
            final = payload
            turns.append({"assistant": text})
        else:
            raise ValueError("Malformed teacher order: " + str(task["id"]))
    score = executor.score(final)
    if not score.get("valid") or score.get("criticalErrors") or score.get("coverage", 0) < 0.999:
        raise ValueError("Teacher failed executor validation: " + canonical({"id": task["id"], "score": score}))
    return turns, score


def dry_run(a):
    env, store, tasks, split, evaluation, manifest = load_inputs(a)
    scores = [teacher_trace(env, store, t)[1] for t in tasks]
    report = {**manifest, "mode": "offline_protocol_only_no_model_or_AWS", "teacherTasks": len(scores),
              "teacherMeanReward": round(statistics.fmean(s["total"] for s in scores), 6),
              "teacherValidRate": statistics.fmean(bool(s["valid"]) for s in scores),
              "trainingConfig": vars(a)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


class Runner:
    def __init__(self, a):
        self.a = a
        self.env, self.store, self.tasks, self.splits, self.evaluation, self.manifest = load_inputs(a)
        # Verify all training teachers before loading a costly model. Held-out teachers
        # are never tokenized or used as optimization targets.
        self.teachers = {str(t["id"]): teacher_trace(self.env, self.store, t)[0] for t in self.splits["train"]}
        self.sft_schedule = balanced_rows(self.splits["train"], a.sft_max_tasks, a.seed, replacement=True)
        self.rl_schedule = balanced_rows(self.splits["train"], a.steps * a.prompts_per_step,
                                        a.seed + 1, replacement=True)
        self.out = Path(a.out)
        self.out.mkdir(parents=True, exist_ok=True)
        if (HERE / "package-manifest.json").is_file():
            shutil.copyfile(HERE / "package-manifest.json", self.out / "package-manifest.json")
        (self.out / "input-manifest.json").write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2))
        (self.out / "frozen-tasks.jsonl").write_text("".join(canonical(t) + "\n" for t in self.tasks))
        (self.out / "training-schedule.json").write_text(json.dumps({
            "weights": TRAIN_WEIGHTS, "sftIdsPerEpoch": [t["id"] for t in self.sft_schedule],
            "sftEpochs": a.sft_epochs, "rlPromptIds": [t["id"] for t in self.rl_schedule],
            "sftUniqueTasks": len({t["id"] for t in self.sft_schedule}),
            "repeatedSourceTasksAreNotIndependentSamples": True}, ensure_ascii=False, indent=2))
        self.started = time.monotonic()
        self.log("inputs", **self.manifest, config=vars(a))
        import torch
        import torch.nn.functional as F
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        self.torch, self.F = torch, F
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required; use --dry-run for local protocol validation")
        random.seed(a.seed)
        torch.manual_seed(a.seed)
        self.tok = AutoTokenizer.from_pretrained(a.model)
        self.tok.padding_side = "left"
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token
        self.end_id = self.tok.convert_tokens_to_ids("<|im_end|>")
        if self.end_id is None or self.end_id == self.tok.unk_token_id:
            raise ValueError("Expected Qwen chat end token")
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
        base = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=quant,
                  torch_dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa")
        self.base_revision = getattr(base.config, "_commit_hash", None)
        base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=True,
                                               gradient_checkpointing_kwargs={"use_reentrant": False})
        base.config.use_cache = False
        self.model = get_peft_model(base, LoraConfig(r=a.lora_r, lora_alpha=2 * a.lora_r,
             lora_dropout=0.0, task_type="CAUSAL_LM", target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                                                   "gate_proj", "up_proj", "down_proj"]))
        self.params = [p for p in self.model.parameters() if p.requires_grad]
        self.opt = torch.optim.AdamW(self.params, lr=a.sft_lr, betas=(0.9, 0.99), weight_decay=0)
        self.started = time.monotonic()
        self.log("model_loaded", model=a.model, revision=self.base_revision,
                 gpu=torch.cuda.get_device_name(), allocatedGiB=round(torch.cuda.memory_allocated() / 2**30, 3),
                 trainableParameters=sum(p.numel() for p in self.params), quantization="nf4-double-bfloat16",
                 packages={p: importlib.metadata.version(p) for p in ("torch", "transformers", "peft", "bitsandbytes")},
                 budgetScope="training/evaluation after model loading; CPU merge excluded")

    def log(self, kind, **fields):
        row = {"kind": kind, "seconds": round(time.monotonic() - self.started, 2), **fields}
        with (self.out / "metrics.jsonl").open("a") as stream:
            stream.write(canonical(row) + "\n")
        print(canonical(row), flush=True)

    def remaining(self):
        return self.a.time_budget - (time.monotonic() - self.started)

    def first_ids(self, task):
        view = self.env.policy_view(task)
        messages = [{"role": "system", "content": self.env.SYSTEM},
                    {"role": "user", "content": view if isinstance(view, str) else canonical(view)}]
        return self.tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)

    def middle_ids(self, results):
        text = "\n<|im_start|>user\n" + canonical({"toolResults": results}) + "<|im_end|>\n<|im_start|>assistant\n"
        return self.tok(text, add_special_tokens=False)["input_ids"]

    def sample(self, id_lists, greedy):
        torch, a = self.torch, self.a
        results = []
        self.model.eval()
        with torch.no_grad():
            for start in range(0, len(id_lists), a.generation_batch):
                chunk = id_lists[start:start + a.generation_batch]
                width = max(map(len, chunk))
                if width + a.max_new > a.max_sequence:
                    raise ValueError("Context exceeds configured sequence limit; never truncate evidence")
                pad = self.tok.pad_token_id
                ids = torch.tensor([[pad] * (width - len(x)) + x for x in chunk], device="cuda")
                mask = torch.tensor([[0] * (width - len(x)) + [1] * len(x) for x in chunk], device="cuda")
                kwargs = {} if greedy else {"temperature": a.temperature, "top_p": 1.0, "top_k": 0}
                out = self.model.generate(input_ids=ids, attention_mask=mask, max_new_tokens=a.max_new,
                          do_sample=not greedy, pad_token_id=pad, eos_token_id=self.end_id, use_cache=True, **kwargs)
                for tokens in out[:, width:].tolist():
                    if self.end_id in tokens:
                        tokens = tokens[:tokens.index(self.end_id) + 1]
                    results.append((tokens, self.tok.decode(tokens, skip_special_tokens=True)))
                del ids, mask, out
        return results

    def rollout(self, tasks, greedy=False):
        episodes = []
        for task in tasks:
            ids = self.first_ids(task)
            episodes.append({"task": task, "ids": ids, "mask": [0] * len(ids), "turns": [], "answer": None,
                             "executor": self.env.Environment(task, self.store), "invalid": False, "done": False})
        for turn in range(self.a.max_turns):
            active = [e for e in episodes if not e["done"]]
            within = []
            for e in active:
                if len(e["ids"]) + self.a.max_new > self.a.max_sequence:
                    e["invalid"], e["done"] = True, True
                    e["failure"] = "context_budget_exceeded"
                else:
                    within.append(e)
            if not within:
                break
            for e, (tokens, text) in zip(within, self.sample([e["ids"] for e in within], greedy)):
                e["ids"].extend(tokens)
                e["mask"].extend([1] * len(tokens))
                e["turns"].append({"assistant": text})
                kind, payload, invalid = self.env.parse_action(text)
                if invalid:
                    e["invalid"], e["done"] = True, True
                elif kind == "answer":
                    e["answer"], e["done"] = payload, True
                elif kind == "tools" and turn + 1 < self.a.max_turns:
                    results = [e["executor"].execute(tool) for tool in payload]
                    e["turns"][-1]["toolResults"] = results
                    middle = self.middle_ids(results)
                    if len(e["ids"]) + len(middle) + self.a.max_new > self.a.max_sequence:
                        # Keep sampled policy tokens for the negative reward, but
                        # never train an oversized context after marking it invalid.
                        e["invalid"], e["done"] = True, True
                        e["failure"] = "context_budget_exceeded"
                    else:
                        e["ids"].extend(middle)
                        e["mask"].extend([0] * len(middle))
                else:
                    e["invalid"], e["done"] = True, True
        for e in episodes:
            e["invalid"] |= not e["done"]
            e["score"] = e["executor"].score(None if e["invalid"] else e["answer"])
            if e["invalid"]:
                e["score"] = {**e["score"], "valid": False, "total": min(-1.0, e["score"]["total"])}
        return episodes

    def teacher_episode(self, task):
        ids = list(self.first_ids(task))
        mask = [0] * len(ids)
        for turn in self.teachers[str(task["id"])]:
            tokens = self.tok(turn["assistant"], add_special_tokens=False)["input_ids"] + [self.end_id]
            ids.extend(tokens)
            mask.extend([1] * len(tokens))
            if "toolResults" in turn:
                tokens = self.middle_ids(turn["toolResults"])
                ids.extend(tokens)
                mask.extend([0] * len(tokens))
        if len(ids) > self.a.max_sequence:
            raise ValueError("Teacher exceeds context budget: " + str(task["id"]))
        return {"ids": ids, "mask": mask}

    def loss(self, episodes, advantages=None, scale=1.0):
        torch = self.torch
        self.model.train()
        total_tokens = sum(sum(e["mask"]) for e in episodes)
        if not total_tokens:
            return 0.0
        value = 0.0
        for start in range(0, len(episodes), self.a.micro_batch):
            chunk = episodes[start:start + self.a.micro_batch]
            width = max(len(e["ids"]) for e in chunk)
            ids = torch.tensor([e["ids"] + [self.tok.pad_token_id] * (width - len(e["ids"])) for e in chunk], device="cuda")
            attention = torch.tensor([[1] * len(e["ids"]) + [0] * (width - len(e["ids"])) for e in chunk], device="cuda")
            policy = torch.tensor([e["mask"] + [0] * (width - len(e["mask"])) for e in chunk], device="cuda", dtype=torch.bool)[:, 1:]
            logits = self.model(input_ids=ids, attention_mask=attention, use_cache=False).logits[:, :-1]
            # Cast only sampled assistant positions, not every tool/context position,
            # to FP32. Full-vocabulary FP32 logits caused excess memory in older runs.
            token_losses = self.F.cross_entropy(logits[policy].float(), ids[:, 1:][policy], reduction="none")
            weights = torch.ones(len(chunk), device="cuda") if advantages is None else torch.tensor(
                advantages[start:start + len(chunk)], device="cuda", dtype=torch.float32)
            loss = (token_losses * weights.unsqueeze(1).expand_as(policy)[policy]).sum() * scale / total_tokens
            loss.backward()
            value += float(loss.detach())
            del logits, token_losses, loss, ids, attention, policy
        return value

    def optimize(self):
        self.torch.nn.utils.clip_grad_norm_(self.params, 1.0, error_if_nonfinite=True)
        self.opt.step()
        self.opt.zero_grad(set_to_none=True)

    def save(self, stage):
        path = self.out / ("adapter-" + stage)
        self.model.save_pretrained(path, safe_serialization=True)
        self.tok.save_pretrained(path)
        self.log("checkpoint", stage=stage, path=str(path))

    def sft(self):
        rows = self.sft_schedule
        completed = 0
        self.opt.zero_grad(set_to_none=True)
        for epoch in range(self.a.sft_epochs):
            for start in range(0, len(rows), self.a.accumulation):
                if self.remaining() < self.a.final_reserve + 300:
                    self.log("sft_budget_stop", completed=completed)
                    return completed
                batch = [self.teacher_episode(t) for t in rows[start:start + self.a.accumulation]]
                loss = self.loss(batch)
                self.optimize()
                completed += len(batch)
                if completed % 16 == 0 or start + self.a.accumulation >= len(rows):
                    self.log("sft", epoch=epoch + 1, completed=completed, loss=round(loss, 6))
        return completed

    @staticmethod
    def summarize(episodes):
        if not episodes:
            return {"episodes": 0, "validRate": None, "schemaRate": None, "formatRate": None, "meanReward": None, "coverage": None,
                    "criticalErrorRate": None, "successRate": None}
        return {"episodes": len(episodes),
                "validRate": statistics.fmean(bool(e["score"].get("valid")) for e in episodes),
                "schemaRate": statistics.fmean(e["score"].get("format", 0) for e in episodes),
                "formatRate": statistics.fmean(e["score"].get("format", 0) for e in episodes),
                "meanReward": statistics.fmean(e["score"]["total"] for e in episodes),
                "coverage": statistics.fmean(e["score"].get("coverage", 0) for e in episodes),
                "criticalErrorRate": statistics.fmean(bool(e["score"].get("criticalErrors")) for e in episodes),
                "successRate": statistics.fmean(bool(e["score"].get("valid")) and not e["score"].get("criticalErrors")
                     and e["score"].get("coverage", 0) >= 0.999 and e["score"]["total"] >= 0.97 for e in episodes)}

    def record(self, episode):
        return {"taskId": episode["task"]["id"], "split": episode["task"]["split"],
                "turns": episode["turns"], "answer": episode["answer"], "score": episode["score"],
                "invalid": episode["invalid"], "failure": episode.get("failure")}

    def evaluate(self, stage):
        summaries = {}
        for split, tasks in self.evaluation.items():
            episodes = []
            with (self.out / f"evaluation-{stage}-{split}.jsonl").open("w") as stream:
                for start in range(0, len(tasks), self.a.generation_batch):
                    if self.remaining() <= 0:
                        break
                    batch = self.rollout(tasks[start:start + self.a.generation_batch], greedy=True)
                    episodes.extend(batch)
                    for e in batch:
                        stream.write(canonical(self.record(e)) + "\n")
                    stream.flush()
            summaries[split] = {**self.summarize(episodes), "expectedEpisodes": len(tasks),
                                "complete": len(episodes) == len(tasks)}
            self.log("evaluation", stage=stage, split=split, **summaries[split])
        return summaries

    def rl(self):
        # Single on-policy update per rollout group. Group-normalized REINFORCE
        # at ratio=1, no PPO replay, no reference KL; do not claim clipped PPO.
        for group in self.opt.param_groups:
            group["lr"] = self.a.lr
        completed = 0
        for step in range(1, self.a.steps + 1):
            if self.remaining() < self.a.final_reserve:
                break
            start = (step - 1) * self.a.prompts_per_step
            prompts = self.rl_schedule[start:start + self.a.prompts_per_step]
            episodes = self.rollout([t for t in prompts for _ in range(self.a.group)])
            used, advantages, flat = [], [], 0
            for offset in range(0, len(episodes), self.a.group):
                members = episodes[offset:offset + self.a.group]
                rewards = [e["score"]["total"] for e in members]
                mean, std = statistics.fmean(rewards), statistics.pstdev(rewards)
                if std < 1e-6:
                    flat += 1
                    continue
                used.extend(members)
                advantages.extend((r - mean) / (std + 1e-4) for r in rewards)
            self.opt.zero_grad(set_to_none=True)
            loss = self.loss(used, advantages) if used else 0.0
            if used:
                self.optimize()
            completed = step
            self.log("rl", step=step, loss=round(loss, 6), flatGroups=flat,
                     updateGroups=len(used) // self.a.group, **self.summarize(episodes))
            if step == 1 or step % 5 == 0:
                with (self.out / "rollouts.jsonl").open("a") as stream:
                    stream.write(canonical({"step": step, "episodes": [self.record(e) for e in episodes]}) + "\n")
        return completed

    def publish_artifacts(self, report):
        selected = self.out / ("adapter-" + report["selectedStage"])
        model_dir = Path(os.environ.get("SM_MODEL_DIR", str(self.out / "model-artifact")))
        model_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(selected, model_dir / "adapter", dirs_exist_ok=True)
        (model_dir / "training-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        if self.a.merge:
            # Reload the unquantized base on CPU; do not merge into NF4 weights.
            from peft import PeftModel
            from transformers import AutoModelForCausalLM
            del self.model, self.opt, self.params
            gc.collect()
            self.torch.cuda.empty_cache()
            base = AutoModelForCausalLM.from_pretrained(self.a.model, revision=self.base_revision,
                       torch_dtype=self.torch.bfloat16, device_map={"": "cpu"}, low_cpu_mem_usage=True)
            merged = PeftModel.from_pretrained(base, selected).merge_and_unload()
            merged.save_pretrained(self.out / "merged", safe_serialization=True, max_shard_size="2GB")
            self.tok.save_pretrained(self.out / "merged")
            self.log("merged", sourceStage=report["selectedStage"], path=str(self.out / "merged"))

    def run(self):
        results = {"base": self.evaluate("base")}
        sft_tasks = self.sft()
        self.save("sft")
        results["sft"] = self.evaluate("sft")
        val = results["sft"]["val"]
        eligible = val["complete"] and val["schemaRate"] >= self.a.min_sft_valid
        rl_steps = self.rl() if eligible and self.remaining() > self.a.final_reserve else 0
        if not eligible:
            self.log("rl_gate_failed", reason="SFT held-out schema rate below frozen threshold", validation=val)
        self.save("rl")
        results["rl"] = self.evaluate("rl")
        def rank(stage):
            row = results[stage]["val"]
            return ((1, -row["criticalErrorRate"], row["successRate"], row["meanReward"])
                    if row["complete"] else (0, -1, -1, -2))
        # Ties retain SFT; test data never selects a stage or affects updates.
        selected = "rl" if rl_steps and rank("rl") > rank("sft") else "sft"
        report = {"schema": "rl-scout-evidence-training-report-v1", "model": self.a.model,
                  "baseRevision": self.base_revision, "storeSha256": self.manifest["storeSha256"],
                  "tasksSha256": self.manifest["tasksSha256"], "sourceJob": os.environ.get("RL_TRAINING_JOB"),
                  "sftExamplesOptimized": sft_tasks, "rlSteps": rl_steps, "rlGatePassed": eligible,
                  "sftUniqueTasksScheduled": len({t["id"] for t in self.sft_schedule}),
                  "samplingWeights": TRAIN_WEIGHTS,
                  "selectedStage": selected, "evaluation": results, "config": vars(self.a),
                  "budgetSeconds": self.a.time_budget, "elapsedSeconds": round(time.monotonic() - self.started, 2),
                  "method": "verified SFT + single-update group-normalized on-policy policy gradient, no reference KL",
                  "claimBoundary": "structured evidence selection only; no visual-model training or automatic deployment"}
        (self.out / "training-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self.publish_artifacts(report)
        self.log("done", selectedStage=selected, sftExamplesOptimized=sft_tasks, rlSteps=rl_steps)


if __name__ == "__main__":
    args = arguments()
    dry_run(args) if args.dry_run else Runner(args).run()
