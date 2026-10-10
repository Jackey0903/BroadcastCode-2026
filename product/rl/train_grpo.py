#!/usr/bin/env python3
"""Multi-turn GRPO for RL-SCOUT on one GPU (SageMaker training container).

Episode: policy may request tools in turn 1, receives tool results from the environment,
answers in turn 2 (or answers directly in turn 1). Sequences are assembled from the exact
token ids the policy sampled plus environment-inserted tokens; only policy tokens carry loss.
On-policy single update per batch, group-normalised advantages, token-level loss, no KL.
"""
import argparse
import json
import os
import random
import statistics
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

import scout_env as env

HERE = Path(__file__).resolve().parent


def arguments():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    p.add_argument("--steps", type=int, default=160)
    p.add_argument("--prompts-per-step", type=int, default=8)
    p.add_argument("--group", type=int, default=8)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--lora-r", type=int, default=32)
    p.add_argument("--max-new", type=int, default=160)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--micro-batch", type=int, default=8)
    p.add_argument("--eval-every", type=int, default=20)
    p.add_argument("--eval-n", type=int, default=96)
    p.add_argument("--final-eval-n", type=int, default=400)
    p.add_argument("--save-every", type=int, default=25)
    p.add_argument("--rollout-every", type=int, default=10)
    p.add_argument("--merge", type=int, default=1)
    p.add_argument("--focus-ratio", type=float, default=0.8)
    p.add_argument("--time-budget", type=int, default=0, help="seconds for the training loop; 0 = no limit")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--data-dir", default=str(HERE / "data"))
    p.add_argument("--out", default=os.environ.get("RL_OUT", "/opt/ml/checkpoints"))
    args, _ = p.parse_known_args()
    return args


class Runner:
    def __init__(self, args):
        self.args = args
        random.seed(args.seed)
        torch.manual_seed(args.seed)
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        shots = env.load_shots(Path(args.data_dir) / "shots.jsonl")
        profiles = json.loads((Path(args.data_dir) / "profiles.json").read_text())
        self.train, _ = env.split(shots)
        self.train_focus = [s for s in self.train if s.get("focus")]
        self.refs = env.References(self.train, profiles)
        sets = env.test_sets(shots)
        rng = random.Random(args.seed)
        third = args.eval_n // 3
        self.eval_set = (rng.sample(sets["h2h"], min(2 * third, len(sets["h2h"])))
                         + rng.sample(sets["league"], min(third, len(sets["league"]))))
        self.final_sets = {name: rng.sample(rows, min(args.final_eval_n, len(rows))) for name, rows in sets.items() if rows}
        self.log("data", train=len(self.train), trainFocus=len(self.train_focus),
                 **{f"test_{k}": len(v) for k, v in sets.items()}, model=args.model)

        self.tok = AutoTokenizer.from_pretrained(args.model)
        self.tok.padding_side = "left"
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token
        self.end_id = self.tok.convert_tokens_to_ids("<|im_end|>")
        base = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16,
                                                    attn_implementation="sdpa").cuda()
        base.gradient_checkpointing_enable()
        base.enable_input_require_grads()
        lora = LoraConfig(r=args.lora_r, lora_alpha=2 * args.lora_r, lora_dropout=0.0, task_type="CAUSAL_LM",
                          target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
        self.model = get_peft_model(base, lora)
        params = [p for p in self.model.parameters() if p.requires_grad]
        self.opt = torch.optim.AdamW(params, lr=args.lr, betas=(0.9, 0.99), weight_decay=0.0)
        self.started = time.time()

    # ---------- logging ----------
    def log(self, kind, **fields):
        row = {"kind": kind, "t": round(time.time() - getattr(self, "started", time.time()), 1), **fields}
        with (self.out / "metrics.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=False), flush=True)

    # ---------- generation ----------
    def prompt_ids(self, messages):
        return self.tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)

    def middle_ids(self, tool_text):
        # What the chat template renders after an assistant turn, then a user turn, then a new assistant turn.
        text = "\n<|im_start|>user\n" + tool_text + "<|im_end|>\n<|im_start|>assistant\n"
        return self.tok(text, add_special_tokens=False)["input_ids"]

    @torch.no_grad()
    def sample(self, id_lists, greedy=False):
        self.model.eval()
        width = max(len(x) for x in id_lists)
        pad = self.tok.pad_token_id
        input_ids = torch.tensor([[pad] * (width - len(x)) + x for x in id_lists], device="cuda")
        attention = torch.tensor([[0] * (width - len(x)) + [1] * len(x) for x in id_lists], device="cuda")
        out = self.model.generate(input_ids=input_ids, attention_mask=attention, max_new_tokens=self.args.max_new,
                                  do_sample=not greedy, temperature=self.args.temperature if not greedy else None,
                                  top_p=1.0 if not greedy else None, top_k=0 if not greedy else None,
                                  pad_token_id=pad, eos_token_id=self.end_id, use_cache=True)
        results = []
        for row in out[:, width:].tolist():
            if self.end_id in row:
                row = row[: row.index(self.end_id) + 1]
            else:
                row = [t for t in row if t != pad]
            results.append((row, self.tok.decode(row, skip_special_tokens=True)))
        return results

    def rollout(self, shots, greedy=False):
        """Run episodes; returns dicts with token ids, policy mask, reward parts and transcript."""
        episodes = []
        for shot in shots:
            messages = env.first_messages(shot)
            ids = self.prompt_ids(messages)
            episodes.append({"shot": shot, "ids": list(ids), "mask": [0] * len(ids),
                             "context": env.observation(shot), "turns": [], "toolNames": [], "invalid": False,
                             "answer": None, "done": False})
        for turn in range(2):
            active = [e for e in episodes if not e["done"]]
            if not active:
                break
            for e, (gen, text) in zip(active, self.sample([e["ids"] for e in active], greedy)):
                e["ids"] += gen
                e["mask"] += [1] * len(gen)
                e["turns"].append(text)
                kind, payload, invalid = env.parse_action(text)
                if kind == "answer":
                    e["answer"], e["done"] = payload, True
                elif kind == "tools" and turn == 0:
                    e["toolNames"], e["invalid"] = payload, e["invalid"] or invalid
                    message = env.tool_message(payload, e["shot"], self.refs)["content"]
                    e["context"] += "\n" + message
                    mid = self.middle_ids(message)
                    e["ids"] += mid
                    e["mask"] += [0] * len(mid)
                else:
                    e["invalid"], e["done"] = True, True
        for e in episodes:
            if not e["done"]:
                e["invalid"] = True
            parts = env.reward(e["answer"], e["shot"]["quality"], e["toolNames"], e["invalid"], e["context"])
            e.update(parts)
            e["quality"] = e["shot"]["quality"]
        return episodes

    # ---------- learning ----------
    def policy_loss(self, episodes, advantages):
        self.model.train()
        total_tokens = sum(sum(e["mask"]) for e in episodes) or 1
        mb = self.args.micro_batch
        loss_value = 0.0
        for start in range(0, len(episodes), mb):
            chunk = episodes[start:start + mb]
            adv = advantages[start:start + mb]
            width = max(len(e["ids"]) for e in chunk)
            pad = self.tok.pad_token_id
            ids = torch.tensor([e["ids"] + [pad] * (width - len(e["ids"])) for e in chunk], device="cuda")
            attn = torch.tensor([[1] * len(e["ids"]) + [0] * (width - len(e["ids"])) for e in chunk], device="cuda")
            mask = torch.tensor([e["mask"] + [0] * (width - len(e["mask"])) for e in chunk],
                                device="cuda", dtype=torch.float32)[:, 1:]
            logits = self.model(input_ids=ids, attention_mask=attn).logits[:, :-1].float()
            logp = -F.cross_entropy(logits.reshape(-1, logits.size(-1)), ids[:, 1:].reshape(-1),
                                    reduction="none").view(len(chunk), -1)
            weights = torch.tensor(adv, device="cuda", dtype=torch.float32).unsqueeze(1)
            loss = -(weights * logp * mask).sum() / total_tokens
            loss.backward()
            loss_value += loss.item()
            del logits, logp
        return loss_value

    def step(self, step):
        a = self.args
        n_focus = round(a.focus_ratio * a.prompts_per_step) if self.train_focus else 0
        shots = random.sample(self.train_focus, min(n_focus, len(self.train_focus)))
        shots += random.sample(self.train, a.prompts_per_step - len(shots))
        batch = [s for s in shots for _ in range(a.group)]
        t0 = time.time()
        episodes = self.rollout(batch)
        t_gen = time.time() - t0
        advantages = []
        for g in range(a.prompts_per_step):
            rewards = [e["total"] for e in episodes[g * a.group:(g + 1) * a.group]]
            mean, std = statistics.fmean(rewards), statistics.pstdev(rewards)
            advantages += [0.0 if std < 1e-6 else (r - mean) / (std + 1e-4) for r in rewards]
        lr = a.lr * min(1.0, (step + 1) / max(1, a.warmup))
        for group in self.opt.param_groups:
            group["lr"] = lr
        self.opt.zero_grad(set_to_none=True)
        loss = self.policy_loss(episodes, advantages)
        torch.nn.utils.clip_grad_norm_([p for p in self.model.parameters() if p.requires_grad], 1.0)
        self.opt.step()
        summary = env.summarize(episodes)
        summary.update({k: round(statistics.fmean(e[k] for e in episodes), 4) for k in ("calibration", "format", "grounded")})
        summary["invalidRate"] = round(statistics.fmean(1.0 if e["invalid"] else 0.0 for e in episodes), 4)
        summary["genTokens"] = round(statistics.fmean(sum(e["mask"]) for e in episodes), 1)
        self.log("train", step=step, loss=round(loss, 5), lr=lr, genSeconds=round(t_gen, 1),
                 stepSeconds=round(time.time() - t0, 1), **summary)
        print(f"METRIC step={step} reward={summary['meanReward']} mae={summary['mae']} "
              f"tools={summary['toolsPerEpisode']} invalid={summary['invalidRate']}", flush=True)
        if step % a.rollout_every == 0:
            group = episodes[: a.group]
            with (self.out / "rollouts.jsonl").open("a") as stream:
                stream.write(json.dumps({"step": step, "shot": group[0]["shot"], "trajectories": [
                    {"turns": e["turns"], "tools": e["toolNames"], "prediction": e["prediction"], "total": e["total"],
                     "calibration": round(e["calibration"], 4), "advantage": round(adv, 3)}
                    for e, adv in zip(group, advantages[: a.group])]}, ensure_ascii=False) + "\n")

    def evaluate(self, step, shots, name="eval", detail=False):
        rows = []
        for start in range(0, len(shots), 64):
            rows += self.rollout(shots[start:start + 64], greedy=True)
        summary = env.summarize(rows)
        self.log(name, step=step, **summary)
        print(f"METRIC eval_step={step} eval_mae={summary['mae']} eval_reward={summary['meanReward']}", flush=True)
        if detail:
            with (self.out / f"{name}-step{step}.jsonl").open("w") as stream:
                for e in rows:
                    stream.write(json.dumps({"shot": e["shot"], "turns": e["turns"], "tools": e["toolNames"],
                                             "prediction": e["prediction"], "quality": e["quality"],
                                             "total": e["total"], "format": e["format"],
                                             "grounded": e["grounded"]}, ensure_ascii=False) + "\n")
        return summary

    def save(self, tag):
        path = self.out / f"adapter-{tag}"
        self.model.save_pretrained(path)
        self.tok.save_pretrained(path)

    def run(self):
        a = self.args
        for name, rows in self.final_sets.items():
            self.evaluate(0, rows, name=f"final_base_{name}", detail=True)
        last = 0
        for step in range(1, a.steps + 1):
            if a.time_budget and time.time() - self.started > a.time_budget:
                self.log("budget_stop", step=step - 1)
                break
            self.step(step)
            last = step
            if step % a.eval_every == 0:
                self.evaluate(step, self.eval_set)
            if step % a.save_every == 0:
                self.save(f"step{step}")
        self.save("final")
        for name, rows in self.final_sets.items():
            self.evaluate(last, rows, name=f"final_trained_{name}", detail=True)
        if a.merge:
            merged = self.model.merge_and_unload()
            merged.save_pretrained(self.out / "merged", safe_serialization=True, max_shard_size="2GB")
            self.tok.save_pretrained(self.out / "merged")
            self.log("merged", path=str(self.out / "merged"))
        self.log("done", seconds=round(time.time() - self.started, 1))


if __name__ == "__main__":
    Runner(arguments()).run()
