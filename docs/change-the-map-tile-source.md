# Change the Map Tile Source

The base map is drawn from raster tiles that are downloaded from a tile server. By default this is OpenStreetMap. You can point the program at a different provider under _Settings → Map Tile Source_.

## URL Format

A raster tile URL is a template with three placeholders that are filled in with the coordinates of each tile:

- `{zoom}` — the zoom level
- `{x}` — the tile column
- `{y}` — the tile row

The default is:

```
https://tile.openstreetmap.org/{zoom}/{x}/{y}.png
```

Most tile providers write the zoom placeholder as `{z}`, so a URL copied from their documentation looks like `https://example.org/{z}/{x}/{y}.png`. That form is accepted as well and is converted into `{zoom}` when you save it. Any other placeholder is an error.

When you save the setting, a sample tile is downloaded from the server. If that fails, the URL is not stored and the error message from the tile server is shown. Your input stays in the form so that you can correct it.

## Providers That Need an API Key

Commercial providers usually require an API key that is part of the URL. With MapTiler, for instance, the URL looks like this:

```
https://api.maptiler.com/maps/outdoor-v4/{z}/{x}/{y}.png?key=YOUR_API_KEY
```

Without a valid key the server responds with an error instead of an image; the check on save will report that.

## Tile Size

Some providers serve tiles of 512 px instead of the usual 256 px. Such tiles are downscaled to 256 px for the generated images (share pictures, heatmap downloads, videos) so that they line up correctly. The map extent is unaffected because the tile numbering is the same for both sizes.

## Licensing

Different sources come with different licensing constraints. It is on you to make sure that you are allowed to use the tiles from the source that you enter. The [list of raster tile providers](https://wiki.openstreetmap.org/wiki/Raster_tile_providers) in the OpenStreetMap wiki gives an overview.
