document.querySelectorAll("[data-detection-class-picker]").forEach((panel) => {
  const boxes = () =>
    panel.querySelectorAll('input[type="checkbox"][name="detection_classes"]');
  panel.querySelector("[data-class-pick-all]")?.addEventListener("click", () => {
    boxes().forEach((el) => {
      el.checked = true;
    });
  });
  panel.querySelector("[data-class-pick-none]")?.addEventListener("click", () => {
    boxes().forEach((el) => {
      el.checked = false;
    });
  });
});
