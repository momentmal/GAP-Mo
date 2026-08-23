const storageKey = "lastSeenVersion";

window.addEventListener("DOMContentLoaded", () => {
  const notice = document.getElementById("version-notice");
  if (!notice) {
    return;
  }

  const current = notice.dataset.version;
  const previous = localStorage.getItem(storageKey);
  localStorage.setItem(storageKey, current);

  if (!previous || previous === current) {
    return;
  }

  notice.querySelector(".version-notice-text").textContent =
    notice.dataset.message.replace("{old}", previous);
  notice.classList.remove("d-none");
});
