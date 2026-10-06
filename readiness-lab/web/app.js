"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const ui = {
    form: $("job-form"), samples: $("sample-options"), start: $("start-job"),
    startLabel: $("start-label"), refreshStatus: $("refresh-status"),
    environmentLabel: $("environment-label"), environmentStatus: $("environment-status"),
    environmentFields: $("environment-fields"), environmentNote: $("environment-note"),
    environmentDetails: $("environment-details"), environmentJson: $("environment-json"),
    status: $("job-status"), stage: $("job-stage"), pollState: $("poll-state"),
    runFields: $("run-fields"), jobId: $("job-id"), runId: $("run-id"), updated: $("last-updated"),
    actions: $("job-actions"), refreshJob: $("refresh-job"), copyRunId: $("copy-run-id"),
    message: $("message-box"), messageTitle: $("message-title"), messageBody: $("message-body"),
    messageDetails: $("message-details"), messageRaw: $("message-raw"),
    jobDetails: $("job-details"), jobJson: $("job-json"), video: $("output-video"),
    videoLink: $("video-link"), placeholder: $("video-placeholder"), videoNote: $("video-note"),
    analysisEmpty: $("analysis-empty"), summary: $("analysis-summary"), observations: $("observation-list"),
    analysisExtra: $("analysis-extra"), evidenceEmpty: $("evidence-empty"), evidence: $("evidence-list"),
  };
  const SUCCESS = new Set(["completed", "complete", "succeeded", "success", "done", "finished"]);
  const FAILURE = new Set(["failed", "error", "cancelled", "canceled"]);
  const STORAGE_KEY = "broadcastcode-readiness-job-v1";
  const POLL_DELAY = 3000;
  const POLL_LIMIT_MS = 30 * 60 * 1000;
  const state = {
    environmentReady: false, busy: false, submitting: false, polling: false,
    jobId: null, runId: null, timer: null, pollErrors: 0, pollStartedAt: 0,
    unavailableSamples: new Set(), lastResponse: null, videoUrl: null,
  };

  function stringify(value) {
    return typeof value === "string" ? value : JSON.stringify(value, null, 2);
  }

  function scalar(value) {
    return ["string", "number", "boolean"].includes(typeof value) ? String(value) : "";
  }

  function first(...values) {
    return values.find((value) => value !== undefined && value !== null && value !== "");
  }

  function safeUrl(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      const url = new URL(value, location.origin);
      return ["https:", "http:"].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  }

  function numericTime(value) {
    if (typeof value === "number") return Number.isFinite(value) && value >= 0 ? value : null;
    if (typeof value !== "string" || !value.trim()) return null;
    if (/^\d+(\.\d+)?$/.test(value)) return Number(value);
    if (/^\d{1,2}:\d{2}(?::\d{2})?(\.\d+)?$/.test(value)) {
      const parts = value.split(":").map(Number);
      if (parts.slice(1).some((part) => part >= 60)) return null;
      return parts.reduce((total, part) => total * 60 + part, 0);
    }
    return null;
  }

  function itemTime(item) {
    if (!item || typeof item !== "object") return null;
    return numericTime(first(item.timeSeconds, item.timestampSeconds, item.sourceTimeSeconds,
      item.time_seconds, item.timestamp_seconds, item.timestamp_sec, item.time_sec, item.timestamp, item.time));
  }

  function displayTime(seconds) {
    if (seconds === null) return "时间未提供";
    const minutes = Math.floor(seconds / 60);
    const remainder = (seconds % 60).toFixed(2).padStart(5, "0");
    return `${String(minutes).padStart(2, "0")}:${remainder}`;
  }

  function clearMessage() {
    ui.message.hidden = true;
    ui.messageRaw.textContent = "";
  }

  function showMessage(title, body, detail, info = false) {
    ui.message.hidden = false;
    ui.message.classList.toggle("info", info);
    ui.messageTitle.textContent = title;
    ui.messageBody.textContent = body;
    ui.messageDetails.hidden = detail === undefined || detail === null;
    ui.messageRaw.textContent = detail === undefined || detail === null ? "" : stringify(detail);
  }

  function setBadge(text, style = "") {
    ui.status.textContent = text;
    ui.status.className = `state-tag ${style}`.trim();
  }

  function syncControls() {
    const selected = ui.form.querySelector('input[name="sample"]:checked');
    ui.start.disabled = !state.environmentReady || state.busy || state.polling || !selected ||
      state.unavailableSamples.has(selected.value);
    ui.startLabel.textContent = state.submitting ? "正在提交…" : state.busy ? "任务处理中…" : "启动实际处理";
    ui.samples.querySelectorAll("input").forEach((input) => {
      input.disabled = state.busy || state.unavailableSamples.has(input.value);
    });
    ui.refreshJob.disabled = state.polling;
    ui.actions.hidden = !state.jobId;
    ui.runFields.hidden = !state.jobId;
    ui.jobId.textContent = state.jobId || "—";
    ui.runId.textContent = state.runId || (state.jobId ? `${state.jobId}（使用 Job ID）` : "—");
  }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.method === "POST" ? 30000 : 20000);
    try {
      const headers = { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers };
      if (["POST", "PUT"].includes(options.method) && typeof options.body === "string") {
        // Lambda function URL origins behind CloudFront OAC require the exact body hash.
        const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(options.body));
        headers["x-amz-content-sha256"] = Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
      }
      const response = await fetch(path, {
        ...options, cache: "no-store", credentials: "same-origin", signal: controller.signal,
        headers,
      });
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); } catch {
        const error = new Error(`服务返回了无法解析的响应（HTTP ${response.status}）。`);
        error.status = response.status;
        error.detail = { path, status: response.status, response: text.slice(0, 1500) };
        throw error;
      }
      if (!response.ok) {
        const error = new Error(scalar(first(data?.message, data?.error?.message, data?.error)) || `请求失败（HTTP ${response.status}）。`);
        error.status = response.status;
        error.detail = { path, status: response.status, response: data };
        throw error;
      }
      if (!data || typeof data !== "object" || Array.isArray(data)) {
        throw new Error("服务未返回预期的 JSON 对象，请检查接口响应。");
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError") {
        throw new Error("本次请求等待超时。服务端任务可能仍在运行。");
      }
      if (error instanceof TypeError && error.message.includes("fetch")) {
        throw new Error("暂时无法连接服务，请检查网络后重新查询。");
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  function addMeta(list, label, value) {
    const printable = scalar(value);
    if (!printable) return;
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = printable;
    row.append(term, description);
    list.append(row);
  }

  async function checkEnvironment() {
    ui.refreshStatus.disabled = true;
    ui.environmentStatus.querySelector(".status-dot").className = "status-dot checking";
    ui.environmentLabel.textContent = "正在检查服务…";
    try {
      const data = await api("/api/status");
      const environment = data.environment && typeof data.environment === "object" ? data.environment : data;
      state.environmentReady = data.ready !== false && !["failed", "error", "offline", "unavailable"].includes(String(data.status).toLowerCase());
      ui.environmentLabel.textContent = state.environmentReady ? "服务已响应，可以开始测试" : "服务已响应，当前尚未就绪";
      ui.environmentStatus.querySelector(".status-dot").className = `status-dot ${state.environmentReady ? "good" : "bad"}`;
      ui.environmentNote.textContent = scalar(data.message) || "这里只确认入口响应；完整链路以本次任务结果为准。";
      ui.environmentFields.replaceChildren();
      addMeta(ui.environmentFields, "区域", first(environment.region, data.region));
      addMeta(ui.environmentFields, "环境", first(typeof data.environment === "string" ? data.environment : null, environment.name, data.service));
      addMeta(ui.environmentFields, "Agent", first(environment.runtimeStatus, data.runtimeStatus));
      addMeta(ui.environmentFields, "模型", first(environment.modelId, data.modelId));
      ui.environmentJson.textContent = stringify(data);
      ui.environmentDetails.hidden = false;
      updateSamples(data.samples);
    } catch (error) {
      state.environmentReady = false;
      ui.environmentLabel.textContent = "服务暂时不可达";
      ui.environmentStatus.querySelector(".status-dot").className = "status-dot bad";
      ui.environmentNote.textContent = error.message;
      ui.environmentFields.replaceChildren();
      ui.environmentDetails.hidden = false;
      ui.environmentJson.textContent = stringify(error.detail || { message: error.message });
    } finally {
      ui.refreshStatus.disabled = false;
      syncControls();
    }
  }

  function updateSamples(samples) {
    state.unavailableSamples.clear();
    document.querySelectorAll("[data-sample]").forEach((element) => { element.textContent = ""; });
    if (!Array.isArray(samples)) return;
    const available = new Map(samples.filter((sample) => typeof sample === "string" || (sample && typeof sample === "object"))
      .map((sample) => typeof sample === "string" ? [sample, true] : [first(sample.id, sample.sample, sample.key), sample.available !== false && sample.enabled !== false]));
    for (const id of ["flagg", "amen"]) {
      const ready = available.get(id) === true;
      if (!ready) state.unavailableSamples.add(id);
      document.querySelector(`[data-sample="${id}"]`).textContent = ready ? "可用" : "未就绪";
    }
    const selected = ui.form.querySelector('input[name="sample"]:checked');
    if (selected && state.unavailableSamples.has(selected.value)) {
      const replacement = [...ui.samples.querySelectorAll("input")].find((input) => !state.unavailableSamples.has(input.value));
      if (replacement) replacement.checked = true;
    }
  }

  function rememberJob(sample) {
    const record = { jobId: state.jobId, sample };
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(record)); } catch { /* Storage may be unavailable. */ }
    try {
      const url = new URL(location.href);
      url.searchParams.set("job", state.jobId);
      history.replaceState(null, "", url);
    } catch { /* The job remains accessible through its displayed ID. */ }
  }

  function forgetJob() {
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* Storage may be unavailable. */ }
    try {
      const url = new URL(location.href);
      url.searchParams.delete("job");
      history.replaceState(null, "", url);
    } catch { /* No job pointer is required to submit a new request. */ }
  }

  function resetResult() {
    state.lastResponse = null;
    state.videoUrl = null;
    ui.video.pause();
    ui.video.removeAttribute("src");
    ui.video.load();
    ui.video.hidden = true;
    ui.videoLink.hidden = true;
    ui.videoLink.removeAttribute("href");
    ui.placeholder.hidden = false;
    ui.videoNote.textContent = "这里播放服务返回的 MP4；页面不会用临时图层代替烧录结果。";
    ui.analysisEmpty.hidden = false;
    ui.summary.hidden = true;
    ui.summary.textContent = "";
    ui.observations.replaceChildren();
    ui.analysisExtra.replaceChildren();
    ui.analysisExtra.hidden = true;
    ui.evidenceEmpty.hidden = false;
    ui.evidence.replaceChildren();
    ui.jobDetails.hidden = true;
    ui.updated.textContent = "—";
  }

  function stopPolling() {
    clearTimeout(state.timer);
    state.timer = null;
  }

  function startPolling() {
    stopPolling();
    state.pollErrors = 0;
    state.pollStartedAt = Date.now();
    pollJob();
  }

  function schedulePoll(delay = POLL_DELAY) {
    stopPolling();
    if (Date.now() - state.pollStartedAt >= POLL_LIMIT_MS) {
      ui.pollState.textContent = "自动查询已暂停，任务可能仍在继续。";
      showMessage("处理等待时间较长", "已暂停自动查询，避免持续请求。可用原任务编号继续查询，不需要重复启动处理。", null, true);
      return;
    }
    state.timer = setTimeout(pollJob, delay);
  }

  async function submitJob(event) {
    event.preventDefault();
    if (ui.start.disabled || state.busy) return;
    const sample = ui.form.querySelector('input[name="sample"]:checked')?.value;
    if (!["flagg", "amen"].includes(sample)) return;
    stopPolling();
    state.busy = true;
    state.submitting = true;
    state.jobId = null;
    state.runId = null;
    forgetJob();
    clearMessage();
    resetResult();
    setBadge("正在提交", "running");
    ui.stage.textContent = "正在提交实际处理请求…";
    ui.pollState.textContent = "等待服务返回任务编号。";
    syncControls();
    try {
      const data = await api("/api/jobs", { method: "POST", body: JSON.stringify({ sample }) });
      if (!data.jobId || typeof data.jobId !== "string") {
        const error = new Error("服务未返回任务编号，无法继续查询。");
        error.detail = data;
        throw error;
      }
      state.jobId = data.jobId;
      state.runId = scalar(data.runId) || null;
      rememberJob(sample);
      renderJob(data);
      startPolling();
    } catch (error) {
      state.busy = false;
      setBadge("提交未确认", "error");
      ui.stage.textContent = "未能获得可查询的任务编号。";
      ui.pollState.textContent = "页面没有自动重新提交。";
      showMessage("提交结果需要核对", `${error.message} 若请求已被服务接收，后台可能仍在处理；请先核对日志或任务记录，再决定是否重新启动。`, error.detail);
    } finally {
      state.submitting = false;
      syncControls();
    }
  }

  async function pollJob() {
    if (!state.jobId || state.polling) return;
    const id = state.jobId;
    state.polling = true;
    syncControls();
    try {
      const data = await api(`/api/jobs/${encodeURIComponent(id)}`);
      if (id !== state.jobId) return;
      state.pollErrors = 0;
      clearMessage();
      renderJob(data);
      const status = String(data.status || "").toLowerCase();
      if (SUCCESS.has(status) || FAILURE.has(status)) {
        state.busy = false;
        stopPolling();
        ui.pollState.textContent = SUCCESS.has(status) ? "服务已返回完成状态。" : "服务已返回终止状态，可查看错误详情。";
      } else {
        ui.pollState.textContent = "每 3 秒查询一次；显示服务真实返回的阶段。";
        schedulePoll();
      }
    } catch (error) {
      if (id !== state.jobId) return;
      if ([400, 404].includes(error.status)) {
        state.busy = false;
        state.pollErrors = 0;
        stopPolling();
        forgetJob();
        setBadge(error.status === 404 ? "任务不存在" : "编号无效", "error");
        ui.stage.textContent = "当前编号无法继续查询，请检查编号或启动一次新处理。";
        ui.pollState.textContent = "已停止查询并清除自动恢复记录。";
        showMessage("任务无法恢复", "该任务编号无效、已过期或不存在。原编号仍显示在上方供复核；现在可以重新选择样片并启动处理。", error.detail || error.message);
        return;
      }
      state.pollErrors += 1;
      if (state.pollErrors <= 3) {
        const delay = POLL_DELAY * 2 ** state.pollErrors;
        ui.pollState.textContent = `暂时未收到状态，${delay / 1000} 秒后重试查询（${state.pollErrors}/3）。`;
        showMessage("暂时无法查询任务", "这不代表后台处理失败；页面只重试读取状态，不会重新提交任务。", error.detail || error.message, true);
        schedulePoll(delay);
      } else {
        ui.pollState.textContent = "自动查询已暂停，可重新查询同一任务。";
        showMessage("查询已暂停，处理结果尚未确认", "网络恢复后点击“重新查询此任务”。本次任务编号已保留，不需要重复启动处理。", error.detail || error.message, true);
      }
    } finally {
      state.polling = false;
      syncControls();
    }
  }

  function renderJob(data) {
    state.lastResponse = data;
    state.runId = scalar(first(data.runId, data.run_id, data.analysis?.runId)) || state.runId;
    ui.jobJson.textContent = stringify(data);
    ui.jobDetails.hidden = false;
    ui.updated.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const status = String(data.status || "unknown").toLowerCase();
    const success = SUCCESS.has(status);
    const failure = FAILURE.has(status);
    const stage = typeof data.stage === "object" ? first(data.stage?.message, data.stage?.name) : data.stage;
    setBadge(success ? "处理完成" : failure ? "处理终止" : ["queued", "pending", "accepted"].includes(status) ? "等待处理" : "正在处理", success ? "success" : failure ? "error" : "running");
    ui.stage.textContent = scalar(stage) || (success ? "本次处理完成。" : failure ? "本次处理未能完成。" : `服务状态：${status}`);
    if (data.analysis !== undefined) renderAnalysis(data.analysis);
    if (data.evidence !== undefined || data.analysis?.evidence !== undefined) renderEvidence(first(data.evidence, data.analysis?.evidence), data);
    if (failure) {
      showMessage("服务报告任务未完成", "请结合任务编号和下方服务响应复核。修复原因后可重新启动一次处理。", data.error || data);
    }
    if (success) {
      const url = safeUrl(data.videoUrl);
      if (url) {
        if (url !== state.videoUrl || ui.video.error) {
          state.videoUrl = url;
          ui.video.src = url;
          ui.video.load();
        }
        ui.video.hidden = false;
        ui.placeholder.hidden = true;
        ui.videoLink.href = url;
        ui.videoLink.hidden = false;
        ui.videoNote.textContent = "服务已返回成片地址。播放即可检查文字是否真实烧录；可打开 MP4 单独查看。";
      } else {
        showMessage("任务完成，但成片地址不可用", "服务没有返回有效的 HTTP(S) 视频地址。可重新查询此任务，并检查原始响应中的 videoUrl。", { videoUrl: data.videoUrl ?? null });
      }
    }
    syncControls();
  }

  function renderAnalysis(analysis) {
    ui.summary.textContent = "";
    ui.summary.hidden = true;
    ui.observations.replaceChildren();
    ui.analysisExtra.replaceChildren();
    ui.analysisExtra.hidden = true;
    ui.analysisEmpty.hidden = analysis !== null && analysis !== "";
    if (analysis === null || analysis === "") return;
    if (typeof analysis === "string") {
      ui.summary.textContent = analysis;
      ui.summary.hidden = false;
      return;
    }
    const summary = scalar(first(analysis.summary, analysis.description, analysis.text));
    if (summary) {
      ui.summary.textContent = summary;
      ui.summary.hidden = false;
    }
    const observations = Array.isArray(analysis) ? analysis : first(analysis.observations, analysis.findings, analysis.events);
    if (Array.isArray(observations)) {
      for (const rawObservation of observations) {
        const observation = rawObservation && typeof rawObservation === "object" ? rawObservation : { text: scalar(rawObservation) || "未提供观察文字" };
        const item = document.createElement("li");
        const time = document.createElement("span");
        time.className = "time-label";
        time.textContent = displayTime(itemTime(observation));
        const content = document.createElement("div");
        const text = document.createElement("p");
        text.textContent = scalar(first(observation.text, observation.observation, observation.description, observation.claim)) || stringify(observation);
        content.append(text);
        if (observation.source) {
          const source = document.createElement("span");
          source.className = "observation-source";
          source.textContent = `来源：${stringify(observation.source)}`;
          content.append(source);
        }
        item.append(time, content);
        ui.observations.append(item);
      }
    }
    if (!summary && (!Array.isArray(observations) || observations.length === 0)) {
      const raw = document.createElement("pre");
      raw.textContent = stringify(analysis);
      ui.analysisExtra.append(raw);
      ui.analysisExtra.hidden = false;
    }
  }

  function renderEvidence(evidence, job) {
    ui.evidence.replaceChildren();
    const frames = Array.isArray(evidence) ? evidence : first(evidence?.frames, evidence?.items);
    ui.evidenceEmpty.hidden = Array.isArray(frames) && frames.length > 0;
    if (!Array.isArray(frames)) return;
    for (const frame of frames) {
      const record = frame && typeof frame === "object" ? frame : { description: scalar(frame) };
      const card = document.createElement("article");
      card.className = "evidence-card";
      const frameUrl = safeUrl(first(record.frameUrl, record.imageUrl, record.url, record.frame_url, record.image_url));
      if (frameUrl) {
        const image = document.createElement("img");
        image.src = frameUrl;
        image.alt = `本次任务来源帧，原片时间 ${displayTime(itemTime(record))}`;
        image.className = "evidence-image";
        image.loading = "lazy";
        image.addEventListener("error", () => { image.hidden = true; }, { once: true });
        card.append(image);
      }
      const content = document.createElement("div");
      content.className = "evidence-content";
      const time = document.createElement("span");
      time.className = "time-label";
      time.textContent = `原片 ${displayTime(itemTime(record))}`;
      const description = document.createElement("p");
      description.textContent = scalar(first(record.description, record.text, record.observation, record.label)) || "服务返回的证据帧";
      content.append(time, description);
      if (record.source) {
        const source = document.createElement("p");
        source.className = "muted";
        source.textContent = `来源：${stringify(record.source)}`;
        content.append(source);
      }
      if (frameUrl) {
        const link = document.createElement("a");
        link.href = frameUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "打开来源帧 ↗";
        content.append(link);
      }
      const outputTime = numericTime(first(record.outputTimeSeconds, record.output_time_seconds));
      const seekTime = outputTime ?? (job.preservesSourceTimeline === true ? itemTime(record) : null);
      if (seekTime !== null) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "跳到成片对应位置";
        button.addEventListener("click", () => {
          if (!state.videoUrl) {
            showMessage("成片尚未就绪", "视频返回后即可跳到对应位置。", null, true);
            return;
          }
          if (Number.isFinite(ui.video.duration) && seekTime > ui.video.duration) {
            showMessage("证据时间超出成片范围", "服务返回的时间映射与视频时长不一致，请复核任务响应。", { seekTime, duration: ui.video.duration });
            return;
          }
          ui.video.currentTime = seekTime;
          ui.video.focus();
          ui.video.scrollIntoView({ behavior: "smooth", block: "center" });
        });
        content.append(button);
      }
      card.append(content);
      ui.evidence.append(card);
    }
  }

  function restoreJob() {
    let record;
    try { record = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null"); } catch { record = null; }
    const queryJob = new URL(location.href).searchParams.get("job");
    const id = queryJob || record?.jobId;
    if (typeof id !== "string" || !id || id.length > 256) return;
    state.jobId = id;
    state.busy = true;
    if (["flagg", "amen"].includes(record?.sample)) {
      ui.samples.querySelector(`input[value="${record.sample}"]`).checked = true;
    }
    setBadge("恢复查询", "running");
    ui.stage.textContent = "正在读取上次任务的真实状态…";
    ui.pollState.textContent = "只恢复查询，不会重新启动处理。";
    syncControls();
    startPolling();
  }

  ui.form.addEventListener("submit", submitJob);
  ui.form.addEventListener("change", syncControls);
  ui.refreshStatus.addEventListener("click", checkEnvironment);
  ui.refreshJob.addEventListener("click", () => { clearMessage(); startPolling(); });
  ui.copyRunId.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(state.runId || state.jobId);
      ui.copyRunId.textContent = "已复制";
      setTimeout(() => { ui.copyRunId.textContent = "复制 Run ID"; }, 2000);
    } catch {
      ui.copyRunId.textContent = "请选中上方编号复制";
    }
  });
  ui.video.addEventListener("error", () => {
    if (!state.videoUrl) return;
    ui.videoNote.textContent = "视频加载失败，任务不一定失败。请先打开 MP4 检查地址，或重新查询以获取最新地址。";
    showMessage("成片暂时无法播放", "请检查视频地址是否过期、访问权限、文件格式或网络。下方原始任务响应可用于复核。", { mediaErrorCode: ui.video.error?.code, jobId: state.jobId });
  });
  window.addEventListener("online", () => {
    if (state.jobId && state.busy && !state.polling) startPolling();
  });
  checkEnvironment();
  restoreJob();
})();
