import L from "leaflet";

const HILLSHADE_EXAGGERATION = 1.5;

/**
 * Adds base and overlay tile layers to a Leaflet map with layer control.
 * 
 * @param {L.Map} map - The Leaflet map instance
 * @param {Object} config - Configuration object
 * @param {number} config.zoom - Primary explorer tile zoom level (drives the default overlay selection)
 * @param {number[]} [config.zoomLevels] - All enabled explorer zoom levels to offer in the layer control (defaults to [zoom])
 * @param {string} config.attribution - Map tile attribution text
 * @param {string} [config.baseLayer='Grayscale'] - Default base layer name
 * @param {string|string[]|null} [config.overlay=['Colorful Cluster', 'Inaccessible Tiles']] - Default overlay strategy or strategies, or null for no overlay; the Mapterhorn hillshade is always added on top of these
 * @param {string[]} [config.ensureOverlays] - Overlays that are added once to already saved preferences, for layers introduced after the user saved them
 * @param {number} [config.activityId] - Activity to highlight in the activity-highlight layer (defaults to the latest one server-side)
 * @param {Object} [config.squarePlanner] - Square planner config (optional)
 * @param {number} config.squarePlanner.x - Square X coordinate
 * @param {number} config.squarePlanner.y - Square Y coordinate
 * @param {number} config.squarePlanner.size - Square size
 * @param {number} [config.historyEventIndex] - Optional cluster-history cutoff index
 */
export function add_layers_to_map(map, config) {
    const {
        zoom,
        zoomLevels = [zoom],
        attribution,
        baseLayer = 'Grayscale',
        overlay = ['Colorful Cluster', 'Inaccessible Tiles'],
        ensureOverlays = [],
        squarePlanner = null,
        historyEventIndex = null,
        activityId = null,
        // Search primitives as a query string. The explorer tiles are then
        // derived for the matching activities instead of the stored state, and
        // the heatmap is restricted to them as well.
        searchQuery = null
    } = config;

    // Get map container ID for localStorage key
    const mapId = map.getContainer().id;
    const storageKey = `map-layers-${mapId}`;

    // Load saved preferences if available
    let saved = {};
    try {
        saved = JSON.parse(localStorage.getItem(storageKey) || '{}');
    } catch (e) {
        console.warn('Failed to load saved map layers:', e);
    }

    const base_maps = {
        "Grayscale": L.tileLayer("/tile/grayscale/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
        "Pastel": L.tileLayer("/tile/pastel/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
        "Color": L.tileLayer("/tile/color/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
        "Inverse Grayscale": L.tileLayer("/tile/inverse_grayscale/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
        "Blank": L.tileLayer("/tile/blank/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution
        }),
    };

    // Build heatmap URL with optional extra args
    // The heatmap and the explorer tiles honor the same filter.
    let heatmap_url = "/heatmap/tile/{z}/{x}/{y}.png";
    if (searchQuery) {
        heatmap_url += `?${searchQuery}`;
    }

    const hillshadeName = "Mapterhorn Hillshade";
    const mapterhornPaneName = "mapterhorn-hillshade";
    if (!map.getPane(mapterhornPaneName)) {
        const pane = map.createPane(mapterhornPaneName);
        pane.style.zIndex = "380";
        pane.style.mixBlendMode = window.gapHillshade?.blendMode ?? "multiply";
        pane.style.pointerEvents = "none";
    }

    if (!(L.gridLayer && L.gridLayer.relief)) {
        console.error("leaflet-relief is required for Mapterhorn hillshade but is not available.");
    }

    const historyParam = Number.isInteger(historyEventIndex)
        ? `&event_index=${historyEventIndex}`
        : '';
    const activityParam = Number.isInteger(activityId)
        ? `&activity_id=${activityId}`
        : '';

    // Explorer overlay strategies. Each becomes one entry per enabled zoom level.
    const explorerStrategies = [
        { name: "Colorful Cluster", strategy: "colorful_cluster", history: true },
        { name: "Max Cluster", strategy: "max_cluster", history: true },
        { name: "First Visit", strategy: "first" },
        { name: "Last Visit", strategy: "last" },
        { name: "Number of Visits", strategy: "visits" },
        { name: "Visited", strategy: "visited" },
        { name: "Missing", strategy: "missing" },
        { name: "New Tiles & Cluster Growth", strategy: "latest_new", activity: true },
    ];
    const inaccessibleName = "Inaccessible Tiles";
    const latestNewActivityName = "New Tiles Activity Track";
    const explorerNames = new Set([
        ...explorerStrategies.map(s => s.name),
        inaccessibleName,
        latestNewActivityName
    ]);

    // Prefix with "Explorer {zoom}" when there is more than one zoom level, so that
    // the entries cluster by zoom level in the layer control.
    const labelFor = (name, z) => zoomLevels.length > 1 ? `Explorer ${z} ${name}` : name;

    const overlay_maps = {
        [hillshadeName]: (L.gridLayer && L.gridLayer.relief)
            ? L.gridLayer.relief({
                mode: "hillshade",
                tileSize: 256,
                elevationUrl: L.GridLayer.Relief.elevationUrls.mapterhorn,
                elevationExtractor: L.GridLayer.Relief.elevationExtractors.mapterhorn,
                attribution: L.GridLayer.Relief.elevationAttributions.mapterhorn,
                hillshadeColorFunction: (intensity) => {
                    const gray = Math.round(255 * intensity);
                    return [gray, gray, gray];
                },
                hillshadeExaggeration: HILLSHADE_EXAGGERATION,
                opacity: window.gapHillshade?.opacity ?? 0.5,
                // Mapterhorn has no elevation tiles above its native zoom; upscale
                // instead of dropping the layer, which Leaflet does when maxZoom is exceeded.
                maxNativeZoom: L.GridLayer.Relief.elevationMaxNativeZooms.mapterhorn,
                maxZoom: 19,
                pane: mapterhornPaneName
            })
            : L.layerGroup(),
    };

    const searchParam = searchQuery ? `&${searchQuery}` : '';
    for (const z of zoomLevels) {
        for (const { name, strategy, history, activity } of explorerStrategies) {
            const extra = (history ? historyParam : '') + (activity ? activityParam : '');
            overlay_maps[labelFor(name, z)] = L.tileLayer(
                `/explorer/${z}/tile/{z}/{x}/{y}.png?color_strategy=${strategy}${extra}${searchParam}`,
                { maxZoom: 19, attribution }
            );
        }
        overlay_maps[labelFor(inaccessibleName, z)] = L.tileLayer(
            `/explorer/${z}/inaccessible-tile/{z}/{x}/{y}.png`,
            { maxZoom: 19, attribution }
        );
        overlay_maps[labelFor(latestNewActivityName, z)] = L.tileLayer(
            `/explorer/${z}/latest-new-tiles-activity/{z}/{x}/{y}.png`
            + (activityParam ? `?${activityParam.slice(1)}` : ''),
            { maxZoom: 19, attribution }
        );
    }

    overlay_maps["Heatmap"] = L.tileLayer(heatmap_url, {
        maxZoom: 19,
        attribution
    });

    // Resolve the default overlay strategies to concrete entries at the primary zoom.
    // The hillshade is on by default everywhere; it only shades the base map and does
    // not compete with the other overlays.
    let selectedOverlay = [
        hillshadeName,
        ...(overlay === null ? [] : [].concat(overlay))
            .map(name => explorerNames.has(name) ? labelFor(name, zoom) : name)
    ];

    if (squarePlanner) {
        const { x, y, size } = squarePlanner;
        overlay_maps["Square Planner"] = L.tileLayer(
            `/explorer/${zoom}/tile/{z}/{x}/{y}.png?color_strategy=square_planner&x=${x}&y=${y}&size=${size}`,
            { maxZoom: 19, attribution }
        );
        selectedOverlay = [hillshadeName, "Square Planner"];
    }

    // Use saved preferences if valid, otherwise fall back to defaults
    const selectedBase = (saved.base && base_maps[saved.base]) ? saved.base : baseLayer;

    // Explorer overlays are remembered by strategy, not by zoom level, so that
    // navigating between explorer pages always shows the strategy at the page's own
    // zoom rather than whichever zoom happened to be active when it was saved.
    const overlayBaseName = (label) => {
        const m = label.match(/^Explorer \d+ (.*)$/);
        return m ? m[1] : label;
    };
    const resolveSavedOverlay = (base) => explorerNames.has(base) ? labelFor(base, zoom) : base;

    // In square planner mode the active overlay must be deterministic and tied to URL
    // parameters; saved overlays can otherwise hide the planner layer.
    const defaultOverlays = selectedOverlay.filter(name => overlay_maps[name]);

    // Overlays that were introduced after the user last saved their preferences are
    // switched on once. Remembering which ones were already offered keeps them off
    // again once the user turns them off deliberately.
    const alreadyEnsured = new Set(Array.isArray(saved.ensured) ? saved.ensured : []);
    const newlyEnsured = [hillshadeName, ...ensureOverlays]
        .filter(name => !alreadyEnsured.has(name));

    let selectedOverlays;
    if (squarePlanner) {
        selectedOverlays = selectedOverlay;
    } else if (saved.overlays && Array.isArray(saved.overlays)) {
        const savedOverlays = [...new Set([...saved.overlays, ...newlyEnsured])]
            .map(resolveSavedOverlay)
            .filter(name => overlay_maps[name]);
        selectedOverlays = savedOverlays.length > 0 ? savedOverlays : defaultOverlays;
    } else {
        // Fall back to default (single overlay as array, or none)
        selectedOverlays = defaultOverlays;
    }

    if (newlyEnsured.length > 0) {
        try {
            const current = JSON.parse(localStorage.getItem(storageKey) || '{}');
            current.ensured = [...alreadyEnsured, ...newlyEnsured];
            if (Array.isArray(current.overlays)) {
                current.overlays = [...new Set([...current.overlays, ...newlyEnsured])];
            }
            localStorage.setItem(storageKey, JSON.stringify(current));
        } catch (err) {
            console.warn('Failed to save ensured overlays:', err);
        }
    }

    base_maps[selectedBase].addTo(map);
    selectedOverlays.forEach(name => overlay_maps[name].addTo(map));

    L.control.layers(base_maps, overlay_maps).addTo(map);

    // Save layer selections to localStorage
    map.on('baselayerchange', (e) => {
        try {
            const current = JSON.parse(localStorage.getItem(storageKey) || '{}');
            current.base = e.name;
            localStorage.setItem(storageKey, JSON.stringify(current));
        } catch (err) {
            console.warn('Failed to save base layer preference:', err);
        }
    });

    // Helper to save all currently active overlays
    function saveOverlays() {
        try {
            const current = JSON.parse(localStorage.getItem(storageKey) || '{}');
            const active = Object.keys(overlay_maps)
                .filter(name => map.hasLayer(overlay_maps[name]))
                .map(overlayBaseName);
            current.overlays = [...new Set(active)];
            localStorage.setItem(storageKey, JSON.stringify(current));
        } catch (err) {
            console.warn('Failed to save overlay preference:', err);
        }
    }

    map.on('overlayadd', saveOverlays);
    map.on('overlayremove', saveOverlays);
}
