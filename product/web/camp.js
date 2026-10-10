"use strict";
/* TRAINING CAMP view. Renders product/data/rl/training-camp.json (built by product/rl/build_camp.py
   from the real SageMaker run). Every number on this page comes from that file. */
(function () {
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}, text) => {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const html = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const fixed = (v, d = 3) => (v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d));
  const TOOL_TAG = { zone_reference: ["Z", "z"], move_reference: ["M", "m"], player_profile: ["P", "p"] };
  const ZONES = { restricted: "篮下", paint: "禁区", midrange: "中距离", corner3: "底角三分", above_break3: "弧顶/两翼三分" };

  function movingAverage(values, window) {
    return values.map((_, i) => {
      const slice = values.slice(Math.max(0, i - window + 1), i + 1).filter((v) => v !== null && v !== undefined);
      return slice.length ? slice.reduce((a, b) => a + b, 0) / slice.length : null;
    });
  }

  function lineChart(svg, steps, values, opts) {
    svg.replaceChildren();
    const W = 640, H = 220, L = 46, R = 70, T = 14, B = 30;
    const valid = values.map((v, i) => [steps[i], v]).filter(([, v]) => v !== null && v !== undefined);
    if (!valid.length) {
      svg.append(svgEl("text", { x: W / 2, y: H / 2, "text-anchor": "middle", class: "chart-axis" }, "WAITING FOR DATA"));
      return;
    }
    const maxStep = Math.max(...steps, 1);
    const lo = opts.min, hi = opts.max;
    const x = (s) => L + (s / maxStep) * (W - L - R);
    const y = (v) => T + (1 - (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * (H - T - B);
    for (let i = 0; i <= 4; i += 1) {
      const v = lo + ((hi - lo) * i) / 4;
      svg.append(svgEl("line", { x1: L, x2: W - R, y1: Math.round(y(v)) + 0.5, y2: Math.round(y(v)) + 0.5, class: "chart-grid" }));
      svg.append(svgEl("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", class: "chart-axis" }, v.toFixed(opts.decimals ?? 2)));
    }
    svg.append(svgEl("text", { x: W - R, y: H - 8, "text-anchor": "end", class: "chart-axis" }, `STEP ${maxStep}`));
    svg.append(svgEl("text", { x: L, y: H - 8, class: "chart-axis" }, "STEP 0"));
    (opts.refs || []).forEach((ref) => {
      if (ref.value === null || ref.value === undefined) return;
      svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(ref.value), y2: y(ref.value), class: "chart-ref" }));
      svg.append(svgEl("text", { x: W - R + 6, y: y(ref.value) + 4, class: "chart-ref-label" }, ref.label));
    });
    const stepped = (pts) => pts.map(([s, v], i) => (i === 0 ? `M${x(s).toFixed(1)} ${y(v).toFixed(1)}`
      : `H${x(s).toFixed(1)} V${y(v).toFixed(1)}`)).join(" ");
    svg.append(svgEl("path", { d: stepped(valid), class: "chart-line ghost" }));
    const smooth = movingAverage(values, 8).map((v, i) => [steps[i], v]).filter(([, v]) => v !== null);
    svg.append(svgEl("path", { d: stepped(smooth), class: "chart-line" }));
    (opts.evals || []).forEach(([s, v]) => {
      if (v === null || v === undefined) return;
      svg.append(svgEl("rect", { x: x(s) - 4, y: y(v) - 4, width: 8, height: 8, class: "chart-eval" }));
    });
    const last = smooth[smooth.length - 1];
    if (last) svg.append(svgEl("text", { x: x(last[0]) + 6, y: y(last[1]) - 8, class: "chart-end" }, last[1].toFixed(opts.decimals ?? 2)));
  }

  function scatter(svg, points, after) {
    svg.replaceChildren();
    const S = 300, P = 28, span = S - 2 * P;
    const map = (v) => P + v * span;
    svg.append(svgEl("rect", { x: P, y: P, width: span, height: span, fill: "none", class: "chart-grid" }));
    svg.append(svgEl("line", { x1: map(0), y1: S - map(0), x2: map(1), y2: S - map(1), class: "scatter-diag" }));
    svg.append(svgEl("text", { x: P, y: S - 6, class: "chart-axis" }, "PREDICTED →"));
    svg.append(svgEl("text", { x: 4, y: P - 10, class: "chart-axis" }, "↑ OFFICIAL"));
    (points || []).forEach(([pred, official]) => {
      svg.append(svgEl("rect", { x: map(pred) - 2, y: S - map(official) - 2, width: 4, height: 4,
        class: `scatter-point${after ? " after" : ""}` }));
    });
    if (!points || !points.length) svg.append(svgEl("text", { x: S / 2, y: S / 2, "text-anchor": "middle", class: "chart-axis" }, "WAITING"));
  }

  function renderGroup(group) {
    const view = $("group-view");
    view.replaceChildren();
    const shot = group.shot;
    const card = html("div", "group-shot");
    card.append(html("p", "eyebrow", `STEP ${group.step}`), html("h3", "", shot.desc));
    const dl = html("dl");
    [["区域", `${ZONES[shot.zone] || shot.zone} · ${shot.type === "3PT" ? "三分" : "两分"}`], ["距篮筐", `${shot.distanceFt} FT`]]
      .forEach(([k, v]) => dl.append(html("dt", "", k), html("dd", "", v)));
    const official = html("div", "official");
    official.append(html("span", "", "官方出手质量（模型看不到）"), html("b", "", fixed(shot.official, 3)));
    card.append(dl, official);

    const body = html("div");
    const rail = html("div", "group-rail");
    [0, 0.25, 0.5, 0.75, 1].forEach((t) => { const tick = html("span", "tick", t.toFixed(2)); tick.style.left = `${t * 100}%`; rail.append(tick); });
    const line = html("span", "official-line"); line.style.left = `${shot.official * 100}%`; rail.append(line);
    const best = Math.max(...group.trajectories.map((t) => t.reward));
    group.trajectories.forEach((t) => {
      if (t.prediction === null || t.prediction === undefined) return;
      const dot = html("span", `dot${t.reward === best ? " best" : t.advantage > 0 ? " up" : ""}`);
      dot.style.left = `${t.prediction * 100}%`;
      rail.append(dot);
    });
    const rows = html("div", "group-rows");
    group.trajectories.forEach((t, i) => {
      const row = html("div", `group-row${t.reward === best ? " best" : ""}`);
      const tools = html("span", "tools");
      if (Array.isArray(t.tools) && t.tools.length) t.tools.forEach((name) => { const [label, cls] = TOOL_TAG[name] || ["?", ""]; tools.append(html("i", cls, label)); });
      else if (typeof t.tools === "number" && t.tools) tools.append(html("em", "", `×${t.tools} TOOLS`));
      else tools.append(html("em", "", "直接作答"));
      const bar = html("span", "bar");
      const fill = html("i", t.reward < 0 ? "neg" : "");
      fill.style.width = `${Math.max(0, Math.min(1, Math.abs(t.reward))) * 100}%`;
      bar.append(fill);
      const adv = html("span", "adv", `${t.advantage > 0 ? "+" : ""}${fixed(t.advantage, 2)}`);
      adv.style.color = t.advantage > 0 ? "var(--ball)" : "var(--dim)";
      row.append(html("span", "n", String(i + 1).padStart(2, "0")), tools,
        html("span", "pred", t.prediction === null || t.prediction === undefined ? "INVALID" : fixed(t.prediction, 2)), bar,
        html("span", "say", t.say || ""));
      row.title = `奖励 ${fixed(t.reward, 3)} · 组内优势 ${fixed(t.advantage, 2)}`;
      rows.append(row);
    });
    const legend = html("div", "group-legend");
    legend.innerHTML = '<span><i style="background:#7fb2ff">Z</i> 区域参考</span><span><i style="background:var(--led)">M</i> 动作参考</span><span><i style="background:var(--ok)">P</i> 球员档案</span><span>条长 = 奖励 · 金框 = 本组最佳</span>';
    body.append(rail, rows, legend);
    view.append(card, body);
  }

  function renderBoard(board, model) {
    const short = String(model || "Qwen").split("/").pop().replace("-Instruct", "");
    const table = $("scoreboard");
    table.replaceChildren();
    const head = html("tr");
    ["选手", "模拟考场 误差", "泛化 误差", "工具 / 回合", "有据率", "奖励"].forEach((t) => head.append(html("th", "", t)));
    const thead = html("thead"); thead.append(head); table.append(thead);
    const rows = [
      ["统计基线", "区域 + 动作均值，不学习", "statZoneMove"],
      ["Claude Sonnet 4.6", "同一工具协议，未训练（抽样 120 题）", "claude"],
      [`${short} 训练前`, "RL 起点", "base"],
      ["RL-SCOUT 训练后", "GRPO 强化学习", "trained"],
    ];
    const value = (set, key, field) => board?.[set]?.[key]?.[field];
    const bestOf = (set) => Math.min(...rows.map(([, , key]) => value(set, key, "mae")).filter((v) => typeof v === "number"));
    const tbody = html("tbody");
    rows.forEach(([name, note, key]) => {
      const tr = html("tr", key === "trained" ? "hero" : "");
      const label = html("td", "", name); label.append(html("small", "", note)); tr.append(label);
      ["h2h", "league"].forEach((set) => {
        const mae = value(set, key, "mae");
        tr.append(html("td", mae !== undefined && mae === bestOf(set) ? "win" : "", fixed(mae, 3)));
      });
      const tools = value("h2h", key, "toolsPerEpisode");
      tr.append(html("td", "", key === "statZoneMove" ? "—" : fixed(tools, 2)));
      tr.append(html("td", "", key === "statZoneMove" ? "—" : fixed(value("h2h", key, "groundedRate"), 2)));
      tr.append(html("td", "", key === "statZoneMove" ? "—" : fixed(value("h2h", key, "meanReward"), 3)));
      tbody.append(tr);
    });
    table.append(tbody);
  }

  function render(data) {
    const curve = data.curve || [];
    const steps = curve.map((c) => c.step);
    const lastStep = steps.length ? steps[steps.length - 1] : 0;
    const level = 1 + Math.floor(lastStep / 15);
    $("camp-lv").textContent = `LV.${String(level).padStart(2, "0")}`;
    $("camp-xp").style.width = `${data.status === "done" ? 100 : ((lastStep % 15) / 15) * 100}%`;
    $("camp-xp-bar").setAttribute("aria-valuenow", String(Math.round(data.status === "done" ? 100 : ((lastStep % 15) / 15) * 100)));
    $("camp-status").textContent = data.status === "done" ? `COMPLETE · ${lastStep} STEPS` : `TRAINING · STEP ${lastStep}`;

    const chips = $("camp-chips");
    chips.replaceChildren();
    const d = data.data || {};
    [["SHOTS", d.shots], ["GAMES", d.games], ["PLAYERS", d.players], ["HOU/DAL GAMES", d.focusGames],
     ["TRAIN", d.train], ["EXAM SET", d.testH2H]].forEach(([k, v]) => {
      if (v === undefined || v === null) return;
      const li = html("li"); li.append(html("b", "", k), document.createTextNode(String(v))); chips.append(li);
    });

    const evals = (data.evalCurve || []).map((e) => [e.step, e.mae]);
    const claude = data.scoreboard?.h2h?.claude?.mae;
    const stat = data.scoreboard?.h2h?.statZoneMove?.mae;
    lineChart($("chart-reward"), steps, curve.map((c) => c.meanReward), { min: -0.2, max: 1, decimals: 1 });
    lineChart($("chart-mae"), steps, curve.map((c) => c.mae), { min: 0, max: 0.5, decimals: 2, evals,
      refs: [{ value: stat, label: "STAT" }, { value: claude, label: "CLAUDE" }] });
    lineChart($("chart-tools"), steps, curve.map((c) => c.toolsPerEpisode), { min: 0, max: 3, decimals: 1 });
    $("curve-note").textContent = steps.length ? `${steps.length} STEPS · 方块 = 测试集评测` : "";

    const tabs = $("group-tabs");
    tabs.replaceChildren();
    (data.groups || []).forEach((group, i, all) => {
      const button = html("button", "", `STEP ${group.step}`);
      button.type = "button";
      button.setAttribute("aria-pressed", String(i === all.length - 1));
      button.addEventListener("click", () => {
        tabs.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
        renderGroup(group);
      });
      tabs.append(button);
    });
    if (data.groups && data.groups.length) renderGroup(data.groups[data.groups.length - 1]);

    renderBoard(data.scoreboard, data.model);
    scatter($("scatter-base"), data.calibration?.base, false);
    scatter($("scatter-trained"), data.calibration?.trained, true);
    const notes = $("camp-honesty");
    notes.replaceChildren();
    (data.honesty || []).concat([`训练任务 ${data.job || "—"} · 模型 ${data.model || "—"} · 数据来源：${d.source || "—"}`])
      .forEach((t) => notes.append(html("li", "", t)));
  }

  async function load() {
    try {
      const response = await fetch("/product/data/rl/training-camp.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`训练数据请求返回 ${response.status}`);
      const data = await response.json();
      $("camp-error").hidden = true;
      render(data);
      if (data.status !== "done") setTimeout(load, 60000);
    } catch (error) {
      $("camp-error").hidden = false;
      $("camp-error").textContent = `训练营数据暂时无法加载：${error.message}`;
      $("camp-status").textContent = "OFFLINE";
    }
  }

  if (typeof module === "object" && module.exports) module.exports = { movingAverage };
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load);
  else load();
})();
