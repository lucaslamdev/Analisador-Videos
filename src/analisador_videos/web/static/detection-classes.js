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

  function clickElement(event) {
    const target = event.target;
    if (target instanceof Element) {
      return target;
    }
    const parent = target && target.parentElement;
    return parent instanceof Element ? parent : null;
  }

  function peopleVehicleSet(panel) {
    const jsonEl = panel.querySelector("[data-people-vehicle-classes-json]");
    if (jsonEl && jsonEl.textContent) {
      try {
        const parsed = JSON.parse(jsonEl.textContent);
        if (Array.isArray(parsed) && parsed.length) {
          return new Set(parsed.map(String));
        }
      } catch (_err) {
        /* usa fallback */
      }
    }

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
      .querySelectorAll('input[type="checkbox"][name="detection_classes"]')
      .forEach((el) => {
        if (!(el instanceof HTMLInputElement)) {
          return;
        }
        const next = Boolean(checkedFor(el));
        if (el.checked === next) {
          return;
        }
        el.checked = next;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
  }

  function applyPreset(panel, preset) {
    if (!(panel instanceof Element)) {
      return;
    }
    if (preset === "all") {
      setCheckboxes(panel, () => true);
      return;
    }
    if (preset === "none") {
      setCheckboxes(panel, () => false);
      return;
    }
    if (preset === "people-vehicles") {
      const pickPeopleVehicles = peopleVehicleSet(panel);
      setCheckboxes(panel, (el) => pickPeopleVehicles.has(el.value));
    }
  }

  function panelFromButton(btn) {
    if (!(btn instanceof Element)) {
      return null;
    }
    return btn.closest("[data-detection-class-picker]");
  }

  function presetFromButton(btn) {
    if (!(btn instanceof Element)) {
      return null;
    }
    return btn.getAttribute("data-class-pick");
  }

  function onPresetClick(event) {
    const el = clickElement(event);
    if (!el) {
      return;
    }
    const btn = el.closest("[data-class-pick]");
    if (!btn) {
      return;
    }
    const panel = panelFromButton(btn);
    const preset = presetFromButton(btn);
    if (!panel || !preset) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    applyPreset(panel, preset);
  }

  window.DetectionClassPicker = { applyPreset };

  document.addEventListener("click", onPresetClick, true);
})();
