const form = document.querySelector("#download-form");
const statusText = document.querySelector("#status");
const log = document.querySelector("#log");
const startButton = document.querySelector("#start-button");
const stopButton = document.querySelector("#stop-button");
const clearLogButton = document.querySelector("#clear-log");
const toolTip = document.querySelector("#tool-tip");
const toolTipMessage = document.querySelector("#tool-tip-message");
const toolRecheckButton = document.querySelector("#tool-recheck");
const downloadList = document.querySelector("#download-list");
const downloadCount = document.querySelector("#download-count");
const downloadPagination = document.querySelector("#download-pagination");
const pageFirstButton = document.querySelector("#page-first");
const pagePrevButton = document.querySelector("#page-prev");
const pageNextButton = document.querySelector("#page-next");
const pageLastButton = document.querySelector("#page-last");
const pageStatus = document.querySelector("#page-status");

let pollTimer = null;
let activeJobId = null;
let currentJobId = null;
let fallbackItems = [];
let currentPage = 1;
let currentRenderedItems = [];
let currentRenderedJobId = "";
let toolTipTimer = null;

const DOWNLOAD_PAGE_SIZE = 4;

const statusLabels = {
  pending: "等待中",
  downloading: "下载中",
  completed: "已完成",
  failed: "失败",
  stopped: "已停止",
};

function setStatus(text, state) {
  statusText.textContent = text;
  statusText.dataset.state = state || "";
}

function setLog(lines) {
  log.textContent = lines.join("\n");
  log.scrollTop = log.scrollHeight;
}

function appendLog(line) {
  const prefix = log.textContent ? "\n" : "";
  log.textContent += `${prefix}${line}`;
  log.scrollTop = log.scrollHeight;
}

function hideToolTip() {
  toolTip.hidden = true;
}

function showToolTip(message, state) {
  if (toolTipTimer) {
    clearTimeout(toolTipTimer);
    toolTipTimer = null;
  }
  toolTip.hidden = false;
  toolTip.dataset.state = state || "";
  toolTipMessage.textContent = message;
}

function formatMissingTools(missing) {
  const labels = {
    python: "Python",
    ffmpeg: "FFmpeg",
  };
  return missing.map((name) => labels[name] || name).join("、");
}

function handleToolResult(result) {
  if (result.ok) {
    showToolTip("前置工具检测通过。", "ok");
    toolTipTimer = setTimeout(hideToolTip, 3000);
    return;
  }
  const missing = formatMissingTools(result.missing || []);
  showToolTip(`缺少前置工具：${missing || "未知工具"}。安装后请点击重新检测。`, "warning");
}

async function checkTools() {
  toolRecheckButton.disabled = true;
  showToolTip("正在检测前置工具...", "checking");
  try {
    const response = await fetch("/api/tools");
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || `工具检测失败：${response.status}`);
    }
    handleToolResult(result);
  } catch (error) {
    showToolTip(error.message || "工具检测失败，请稍后重新检测。", "error");
  } finally {
    toolRecheckButton.disabled = false;
  }
}

function clearItems() {
  downloadCount.textContent = "0 项";
  downloadList.innerHTML = '<div class="empty-state">提交下载后会在这里显示每一项的进度</div>';
  downloadPagination.hidden = true;
  currentPage = 1;
  currentRenderedItems = [];
  currentRenderedJobId = "";
}

function parseEpisodeSeeds(selection) {
  const text = String(selection || "").trim();
  if (!text || text.toLowerCase() === "all") {
    return [1];
  }

  const episodes = new Set();
  text.split(",").forEach((rawPart) => {
    const part = rawPart.trim();
    if (!part) {
      return;
    }
    if (part.includes("-")) {
      const [startText, endText] = part.split("-", 2);
      const start = Number(startText);
      const end = Number(endText);
      if (Number.isInteger(start) && Number.isInteger(end) && start > 0 && end >= start) {
        for (let episode = start; episode <= end; episode += 1) {
          episodes.add(episode);
        }
      }
      return;
    }
    const episode = Number(part);
    if (Number.isInteger(episode) && episode > 0) {
      episodes.add(episode);
    }
  });

  return Array.from(episodes).sort((a, b) => a - b);
}

function seedItemsFromPayload(payload) {
  if (/\/audio\/am/i.test(payload.url || "") && !String(payload.episodes || "").trim()) {
    return [
      {
        id: "loading",
        episode: 1,
        name: "正在读取合集列表",
        status: "downloading",
        progress: 0,
        error: null,
      },
    ];
  }

  const episodes = parseEpisodeSeeds(payload.episodes);
  const seededEpisodes = episodes.length ? episodes : [1];
  return seededEpisodes.map((episode) => ({
    id: String(episode),
    episode,
    name: `下载项 ${episode}`,
    status: "pending",
    progress: 0,
    error: null,
  }));
}

function finalizeFallbackItems(status) {
  if (!fallbackItems.length) {
    return [];
  }
  const finalStatus = status === "completed" ? "completed" : "failed";
  return fallbackItems.map((item) => {
    if (item.status !== "pending" && item.status !== "downloading") {
      return item;
    }
    return {
      ...item,
      status: finalStatus,
      progress: finalStatus === "completed" ? 100 : item.progress,
      error: finalStatus === "failed" ? item.error || "下载失败" : null,
    };
  });
}

function createTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  element.className = className;
  element.textContent = text;
  return element;
}

function getPageCount(items) {
  return Math.max(1, Math.ceil(items.length / DOWNLOAD_PAGE_SIZE));
}

function clampPage(page, pageCount) {
  return Math.max(1, Math.min(page, pageCount));
}

function getPageItems(items, page) {
  const start = (page - 1) * DOWNLOAD_PAGE_SIZE;
  return items.slice(start, start + DOWNLOAD_PAGE_SIZE);
}

function updatePagination(items) {
  const pageCount = getPageCount(items);
  currentPage = clampPage(currentPage, pageCount);
  downloadPagination.hidden = items.length <= DOWNLOAD_PAGE_SIZE;
  pageStatus.textContent = `第 ${currentPage} / ${pageCount} 页`;
  pageFirstButton.disabled = currentPage <= 1;
  pagePrevButton.disabled = currentPage <= 1;
  pageNextButton.disabled = currentPage >= pageCount;
  pageLastButton.disabled = currentPage >= pageCount;
}

function renderItems(items, jobId) {
  currentRenderedItems = items;
  currentRenderedJobId = jobId;
  downloadCount.textContent = `${items.length} 项`;
  downloadList.innerHTML = "";

  if (!items.length) {
    clearItems();
    return;
  }

  updatePagination(items);
  getPageItems(items, currentPage).forEach((item) => {
    const status = item.status || "pending";
    const progress = Number(item.progress || 0);
    const row = document.createElement("article");
    row.className = `download-item download-item--${status}`;

    const main = document.createElement("div");
    main.className = "download-main";
    main.appendChild(createTextElement("div", "download-name", item.name || `Item ${item.id}`));

    const metaParts = [statusLabels[status] || status, `${progress.toFixed(progress % 1 ? 1 : 0)}%`];
    if (item.error) {
      metaParts.push(item.error);
    }
    main.appendChild(createTextElement("div", "download-meta", metaParts.join(" · ")));

    const track = document.createElement("div");
    track.className = "progress-track";
    const fill = document.createElement("div");
    fill.className = "progress-fill";
    fill.style.width = `${Math.max(0, Math.min(100, progress))}%`;
    track.appendChild(fill);
    main.appendChild(track);
    row.appendChild(main);

    const action = document.createElement("button");
    action.type = "button";
    action.className = "retry-button";
    action.dataset.itemId = item.id;
    action.dataset.jobId = jobId;
    if (status === "failed") {
      action.textContent = "重新下载";
    } else {
      action.textContent = statusLabels[status] || status;
      action.disabled = true;
    }
    row.appendChild(action);
    downloadList.appendChild(row);
  });
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function pollJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error(`读取任务状态失败：${response.status}`);
  }

  const job = await response.json();
  setLog(job.logs || []);
  let items = job.items || [];
  if (!items.length && fallbackItems.length) {
    items = job.status === "running" ? fallbackItems : finalizeFallbackItems(job.status);
  }
  renderItems(items, job.id);

  if (job.status === "running") {
    setStatus("Downloading", "running");
    return;
  }

  stopPolling();
  activeJobId = null;
  startButton.disabled = false;
  stopButton.disabled = true;
  if (job.status === "completed") {
    setStatus("Completed", "completed");
  } else if (job.status === "stopped") {
    setStatus("Stopped", "failed");
  } else {
    setStatus("Failed", "failed");
  }
}

function startPolling(jobId) {
  stopPolling();
  activeJobId = jobId;
  currentJobId = jobId;
  pollTimer = setInterval(() => {
    if (activeJobId) {
      pollJob(activeJobId).catch((error) => {
        stopPolling();
        activeJobId = null;
        startButton.disabled = false;
        setStatus("Failed", "failed");
        appendLog(error.message);
      });
    }
  }, 1000);
  return pollJob(activeJobId);
}

async function startDownload(payload) {
  const response = await fetch("/api/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `启动失败：${response.status}`);
  }
  return data.job_id;
}

async function retryItem(jobId, itemId) {
  const response = await fetch(`/api/jobs/${jobId}/items/${itemId}/retry`, {
    method: "POST",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `重试失败：${response.status}`);
  }
  return data.job_id;
}

async function stopJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}/stop`, {
    method: "POST",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `停止失败：${response.status}`);
  }
  return data.job_id;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  stopPolling();

  const data = new FormData(form);
  const payload = {
    url: String(data.get("url") || "").trim(),
    media: String(data.get("media") || "auto"),
    episodes: String(data.get("episodes") || "").trim(),
    output: String(data.get("output") || "").trim(),
  };

  startButton.disabled = true;
  stopButton.disabled = false;
  setStatus("Starting", "running");
  setLog([]);
  currentPage = 1;
  fallbackItems = seedItemsFromPayload(payload);
  renderItems(fallbackItems, currentJobId || "");

  try {
    currentJobId = await startDownload(payload);
    appendLog(`Job started: ${currentJobId}`);
    await startPolling(currentJobId);
  } catch (error) {
    startButton.disabled = false;
    stopButton.disabled = true;
    setStatus("Failed", "failed");
    appendLog(error.message);
  }
});

clearLogButton.addEventListener("click", () => {
  setLog([]);
});

toolRecheckButton.addEventListener("click", () => {
  checkTools();
});

pageFirstButton.addEventListener("click", () => {
  if (currentPage <= 1) {
    return;
  }
  currentPage = 1;
  renderItems(currentRenderedItems, currentRenderedJobId);
});

pagePrevButton.addEventListener("click", () => {
  if (currentPage <= 1) {
    return;
  }
  currentPage -= 1;
  renderItems(currentRenderedItems, currentRenderedJobId);
});

pageNextButton.addEventListener("click", () => {
  const pageCount = getPageCount(currentRenderedItems);
  if (currentPage >= pageCount) {
    return;
  }
  currentPage += 1;
  renderItems(currentRenderedItems, currentRenderedJobId);
});

pageLastButton.addEventListener("click", () => {
  const pageCount = getPageCount(currentRenderedItems);
  if (currentPage >= pageCount) {
    return;
  }
  currentPage = pageCount;
  renderItems(currentRenderedItems, currentRenderedJobId);
});

downloadList.addEventListener("click", async (event) => {
  const button = event.target.closest(".retry-button");
  if (!button || button.disabled) {
    return;
  }

  const jobId = button.dataset.jobId || currentJobId;
  const itemId = button.dataset.itemId;
  if (!jobId || !itemId) {
    return;
  }

  button.disabled = true;
  button.textContent = "重试中";
  setStatus("Retrying", "running");
  startButton.disabled = true;

  try {
    const retryJobId = await retryItem(jobId, itemId);
    appendLog(`Retrying item ${itemId}`);
    stopButton.disabled = false;
    await startPolling(retryJobId);
  } catch (error) {
    startButton.disabled = false;
    stopButton.disabled = true;
    setStatus("Failed", "failed");
    appendLog(error.message);
  }
});

checkTools();

stopButton.addEventListener("click", async () => {
  if (!currentJobId) {
    return;
  }

  stopButton.disabled = true;
  setStatus("Stopping", "running");
  try {
    await stopJob(currentJobId);
    appendLog("Stopping current download...");
    await pollJob(currentJobId);
  } catch (error) {
    appendLog(error.message);
    if (activeJobId) {
      stopButton.disabled = false;
    }
  }
});
