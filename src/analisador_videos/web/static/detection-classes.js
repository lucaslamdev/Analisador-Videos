(function () {
  const PEOPLE_VEHICLE_FALLBACK = new Set([
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
  ]);

  function peopleVehicleSet(panel) {
    const raw =
      panel.getAttribute("data-people-vehicle-classes") ||
      panel.dataset.peopleVehicleClasses ||
      "";
    if (!raw) {
      return PEOPLE_VEHICLE_FALLBACK;
    }

    const trimmed = raw.trim();
    if (trimmed.startsWith("[")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed) && parsed.length) {
          return new Set(parsed.map(String));
        }
      } catch (_err) {
        /* fallback abaixo */
      }
    }

    const fromAttr = trimmed
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return fromAttr.length ? new Set(fromAttr) : PEOPLE_VEHICLE_FALLBACK;
  }

  function setCheckboxes(panel, checkedFor) {
    panel
      .querySelectorAll('input[name="detection_classes"]')
      .forEach((el) => {
        if (el instanceof HTMLInputElement) {
          el.checked = checkedFor(el);
        }
      });
  }

  function applyPreset(panel, preset) {
    if (preset === "all") {
      setCheckboxes(panel, () => true);
      return;
    }
    if (preset === "none") {
      setCheckboxes(panel, () => false);
      return;
    }
    const pickPeopleVehicles = peopleVehicleSet(panel);
    setCheckboxes(panel, (el) => pickPeopleVehicles.has(el.value));
  }

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }

    const btn = target.closest(
      "[data-class-pick-all], [data-class-pick-none], [data-class-pick-people-vehicles]"
    );
    if (!btn) {
      return;
    }

    const panel = btn.closest("[data-detection-class-picker]");
    if (!panel) {
      return;
    }

    event.preventDefault();

    if (btn.hasAttribute("data-class-pick-all")) {
      applyPreset(panel, "all");
    } else if (btn.hasAttribute("data-class-pick-none")) {
      applyPreset(panel, "none");
    } else {
      applyPreset(panel, "people-vehicles");
    }
  });
})();
