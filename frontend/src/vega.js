import vegaEmbed from "vega-embed";

// Vega-Lite's `width: "container"` compiles down to a `width` signal that only
// re-evaluates on `window:resize`. That misses two cases we rely on: a chart
// embedded into a hidden Bootstrap tab pane measures a container of width zero
// and stays at the fallback width forever, and a chart whose column changes
// size without the window changing never follows. Feeding the observed
// container size into the signal covers both.
export function embedChart(target, spec, options = {}) {
  return vegaEmbed(target, spec, options).then((result) => {
    if (isResponsive(spec)) {
      observeContainerWidth(resolve(target), result.view);
    }
    return result;
  });
}

function resolve(target) {
  return typeof target === "string" ? document.querySelector(target) : target;
}

function isResponsive(spec) {
  if (spec.width === "container") {
    return true;
  }
  // Compiled Vega: vl-convert turns the container width into this signal.
  return (spec.signals ?? []).some(
    (signal) =>
      signal.name === "width" &&
      typeof signal.init === "string" &&
      signal.init.includes("containerSize"),
  );
}

function observeContainerWidth(element, view) {
  if (!element || typeof ResizeObserver === "undefined") {
    return;
  }
  let applied = null;
  new ResizeObserver(() => {
    // Read through the view's own container so we measure exactly what
    // `containerSize()` would have measured.
    const width = view.container()?.clientWidth ?? 0;
    if (width > 0 && width !== applied) {
      applied = width;
      view.signal("width", width).run();
    }
  }).observe(element);
}
