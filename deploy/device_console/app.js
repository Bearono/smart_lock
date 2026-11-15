const $ = (id) => document.getElementById(id);
const labels = {
  live_front: "真人 · 正面",
  live_angle: "真人 · 轻微侧脸",
  live_dim: "真人 · 较暗光线",
  screen_photo: "手机照片",
  print_photo: "打印照片",
  empty: "空画面",
  multiple: "多人画面",
};
let state = { busy: false, history: [] },
  csrf = "",
  timer,
  counting = false,
  submitting = false,
  currentId = "",
  clientMessage = "";
const time = (value) =>
  new Date(value).toLocaleTimeString("zh-CN", { hour12: false });
function controls() {
  $("shoot").disabled = !csrf || state.busy || counting || submitting;
  $("sample").disabled = $("delay").disabled =
    state.busy || counting || submitting;
  $("cancel").hidden = !counting;
  $("countdown").hidden = !counting;
}
function cancel() {
  clearTimeout(timer);
  counting = false;
  clientMessage = "已取消，尚未拍摄";
  controls();
  $("status").textContent = clientMessage;
  $("announce").textContent = "拍摄已取消";
}
async function shoot() {
  if (state.busy || counting || submitting || !csrf) return;
  clientMessage = "";
  const deadline = performance.now() + Number($("delay").value) * 1000;
  const label = $("sample").value;
  counting = true;
  controls();
  const tick = async () => {
    if (document.hidden) return cancel();
    const remaining = Math.max(
      0,
      Math.ceil((deadline - performance.now()) / 1000),
    );
    $("count").textContent = remaining;
    $("status").textContent = remaining + " 秒后拍摄";
    if (remaining) {
      timer = setTimeout(tick, 100);
      return;
    }
    counting = false;
    submitting = true;
    controls();
    $("status").textContent = "正在拍摄…";
    $("announce").textContent = "正在拍摄";
    try {
      const response = await fetch("/api/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Test-CSRF": csrf },
        body: JSON.stringify({ label }),
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error("拍摄请求未受理，请稍后重试。");
      await poll();
    } catch (error) {
      clientMessage = "拍摄请求未确认，请先查看测试记录再重试。";
      $("status").textContent = clientMessage;
    } finally {
      submitting = false;
      controls();
    }
  };
  tick();
}
function node(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}
function render() {
  controls();
  $("connection").textContent = state.busy ? "设备处理中" : "本机已连接";
  const latest = state.history[0];
  if (state.phase === "capturing" || (latest && !latest.snapshot)) {
    currentId = "";
    $("photo").hidden = true;
    $("placeholder").hidden = false;
  } else if (latest && latest.snapshot && currentId !== latest.id) {
    currentId = latest.id;
    $("photo").src = "/image/" + latest.id;
    $("photo").hidden = false;
    $("placeholder").hidden = true;
  }
  if (!counting && !submitting) {
    $("status").textContent =
      state.phase === "capturing"
        ? "正在拍摄…"
        : state.phase === "analyzing"
          ? "照片已拍好，正在检测…"
          : clientMessage ||
            state.error ||
            (latest ? "本次测试完成" : "等待你按快门");
    $("dot").className =
      "dot " +
      (state.busy
        ? "working"
        : state.error
          ? "failed"
          : latest
            ? "success"
            : "");
    if (latest)
      $("receipt").textContent =
        "测试 " +
        latest.id.slice(0, 8) +
        " · " +
        labels[latest.label] +
        " · " +
        time(latest.received_at || latest.started_at);
  }
  $("total").textContent = state.history.length + " 次";
  if (state.busy) {
    $("results").replaceChildren(
      node("h3", "本次检测"),
      node(
        "p",
        state.phase === "analyzing"
          ? "照片已显示，可放松姿势。检测中…"
          : "等待这次照片…",
      ),
    );
  } else if (latest && latest.analysis) {
    const a = latest.analysis,
      results = $("results");
    results.replaceChildren(node("h3", "本次检测"));
    for (const [name, value] of [
      ["人脸数量", a.face_count],
      [
        "身份匹配",
        a.identity === state.expected
          ? "匹配 " + state.expected
          : "未匹配 " + state.expected,
      ],
      ["相似度", a.similarity.toFixed(3) + " / 0.900"],
      ["防伪分数", a.pad_score.toFixed(3) + " / 0.800"],
    ]) {
      const row = node("div", "", "metric");
      row.append(node("span", name), node("b", value));
      results.append(row);
    }
    results.append(
      node(
        "p",
        latest.sample_passed
          ? "本次样本检查通过"
          : a.face_count !== 1
            ? "请保证画面中只有一张完整人脸"
            : "本次样本未通过检查",
        "verdict" + (latest.sample_passed ? "" : " warning"),
      ),
    );
  } else if (latest) {
    $("results").replaceChildren(
      node("h3", "本次检测"),
      node("p", "本次没有检测结果，请检查设备后重试。"),
    );
  }
  if (state.history.length) {
    $("trials").replaceChildren();
    for (const item of state.history) {
      const row = node("div", "", "trial"),
        detail = node("div", labels[item.label]);
      detail.append(
        node("small", time(item.started_at) + " · " + item.id.slice(0, 8)),
      );
      row.append(
        detail,
        node(
          "span",
          item.status === "analyzing"
            ? "检测中"
            : item.status === "failed"
              ? "未完成"
              : item.sample_passed
                ? "样本通过"
                : "样本未通过",
        ),
      );
      $("trials").append(row);
    }
  }
}
async function poll() {
  try {
    const response = await fetch("/api/state", {
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) throw new Error();
    state = await response.json();
    csrf = state.csrf;
    render();
  } catch {
    csrf = "";
    controls();
    $("connection").textContent = "测试工具未连接";
  }
}
$("shoot").addEventListener("click", shoot);
$("cancel").addEventListener("click", cancel);
document.addEventListener("visibilitychange", () => {
  if (document.hidden && counting) cancel();
});
window.addEventListener("pagehide", () => clearTimeout(timer));
poll();
setInterval(poll, 1500);
