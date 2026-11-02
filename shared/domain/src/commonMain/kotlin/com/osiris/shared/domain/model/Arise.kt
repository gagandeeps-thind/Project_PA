package com.osiris.shared.domain.model

/** Base map look on the Arise tab. */
enum class MapStyle(val label: String) { STANDARD("Standard"), SATELLITE("Satellite"), HYBRID("Hybrid"), WINTER("Winter") }

/** Overlays that can be on together. */
enum class Overlay(val label: String) { POIS("POIs"), BIKE_LANES("Bike lanes") }

/** Activity heatmaps; one at a time. */
enum class Heatmap(val wire: String, val label: String) {
    GLOBAL("global", "Global run"),
    WEEKLY("weekly", "Weekly run"),
    NIGHT("night", "Night run"),
    PERSONAL("personal", "Personal"),
}

/** Slope layers drawn from elevation; one at a time. */
enum class TerrainLayer(val label: String) { AVALANCHE("Avalanche gradient"), GRADIENT("Gradient"), ASPECT("Aspect") }
