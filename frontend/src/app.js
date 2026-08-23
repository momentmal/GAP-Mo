import L from "leaflet";
import "leaflet/dist/leaflet.css";

window.L = L;

// These plugins extend the shared `leaflet` module (and, for the two that
// only ship a UMD build, the `window.L` global assigned above).
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import "leaflet.fullscreen";
import "leaflet.fullscreen/dist/Control.FullScreen.css";
import "leaflet-relief";
import "leaflet-simplestyle";

import "bootstrap/dist/css/bootstrap.min.css";
import bootstrap from "bootstrap/dist/js/bootstrap.bundle.min.js";
window.bootstrap = bootstrap;
import "./bootstrap-dark-mode.js";
import "./version-notice.js";

import vegaEmbed from "vega-embed";
window.vegaEmbed = vegaEmbed;

import "table-sort-js";

import { progressMarkerIcon } from "./progress-markers.js";
window.progressMarkerIcon = progressMarkerIcon;

import "./app.css";
