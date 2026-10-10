"use strict";

// Standalone formal-film controls; no creator API or practice catalog is loaded.
const formalExamPlayer = document.getElementById("formal-exam-player");
window.addEventListener("pagehide", () => formalExamPlayer.pause());

// Keyboard playback supplements native video controls.
document.addEventListener("keydown", (event) => {
  if (document.getElementById("watch-view").hidden || event.ctrlKey || event.metaKey || event.altKey) return;
  if (![" ", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
  if (event.target.closest("input,textarea,select,button,a,summary,[contenteditable]")) return;
  event.stopImmediatePropagation();
  if (event.target === formalExamPlayer) return; // Keep native video controls.
  event.preventDefault();
  if (event.key === " ") {
    if (formalExamPlayer.paused) formalExamPlayer.play().catch(() => {});
    else formalExamPlayer.pause();
  } else if (event.key.startsWith("Arrow") && Number.isFinite(formalExamPlayer.duration)) {
    const delta = event.key === "ArrowRight" ? 5 : -5;
    formalExamPlayer.currentTime = Math.max(0, Math.min(formalExamPlayer.duration, formalExamPlayer.currentTime + delta));
  }
}, true);
