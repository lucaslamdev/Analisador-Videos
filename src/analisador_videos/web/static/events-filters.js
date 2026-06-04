(function () {
  const form = document.getElementById("events-filter-form");
  if (!form) return;

  const selects = {
    batch: form.querySelector('[name="batch"]'),
    video_id: form.querySelector('[name="video_id"]'),
    class: form.querySelector('[name="class"]'),
  };

  function setAll(select, selected) {
    if (!select) return;
    for (const opt of select.options) {
      opt.selected = selected;
    }
  }

  form.querySelectorAll("[data-filter-select-all]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-filter-select-all");
      setAll(selects[key], true);
    });
  });

  form.querySelectorAll("[data-filter-clear]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-filter-clear");
      setAll(selects[key], false);
    });
  });

  const clearAll = form.querySelector('[data-filter-action="clear-all"]');
  if (clearAll) {
    clearAll.addEventListener("click", () => {
      Object.values(selects).forEach((sel) => setAll(sel, false));
      window.location.href = "/events";
    });
  }
})();
