# Tested publication profile

The analyzer reports every layer and selects a renderer explicitly. A package
is a bounded local copy; it grants no access by itself. The server supplies its
own resource/renderer/asset binding and reads sharing from the native catalog.

| Input | Current behavior |
|---|---|
| Local GeoJSON Point, LineString, Polygon | Up to 10,000 2D features in the declared 0–4 geographic test extent; copy hashes and attributes/geometries are checked. |
| Simple opaque circle/square, line and polygon symbols; categorized field values | Native QML and SLD export; actual GeoServer and QGIS map outputs are compared with spatial pixel probes. |
| `upper("label")` using the retained QGIS Vera font | QGIS Server selected; native SLD rejection recorded. Arbitrary expressions are rejected. |
| One-band Byte GeoTIFF with grayscale style | Copied and reopened with exact known samples; QGIS Server selected. Raster translation to GeoServer is outside this profile. |
| Foreign/registered provider, URL, credential-bearing datasource, path outside copy root, symlink | Rejected. Registered references need the later server source-registration workflow. |
| Renamed VRT/XML or GeoJSON foreign members, nonfinite/Z/M/out-of-profile coordinates | Rejected before copying to the serving project. Wider geometry/CRS support is unimplemented here. |
| SVG/plugin symbol, data-defined style, blend/effect, unapproved expression/font, HTML label/background | Rejected with a diagnostic; no silent flattening or uncontrolled asset fetch. |
| Joins, subset filters, auxiliary/temporal layers, scale visibility | Rejected; copying the unfiltered source would change meaning or expose omitted features. |
| Project macros, layouts, nonempty attachments | Rejected or excluded by the declared clean-project profile before serving. Author macros are never executed. |
| Long/colliding Shapefile field names or UTF-8 values above 254 bytes | GeoServer comparison import excluded; QGIS preserves the GeoJSON copy. Native fixture export warnings about field width 255→254 are retained, and actual fixture values/geometry are compared after conversion. |

The ZIP manifest records each asset path, content hash, byte length and media
type. Member count, uncompressed size, compression ratio, duplicate/traversal
paths, symlinks, unknown files and mismatched hashes are rejected. GDAL's
generated `.tif.aux.xml` supports only numeric statistics for band 1; external
references and other XML structures are excluded. The font is a pinned runtime
dependency with a declaration, not a silently embedded/relicensed asset.

The Shapefile comparison explicitly records OGR's single-to-one-part-multipart
promotion and its clockwise polygon ring convention. After those declared
representation changes, original attributes, coordinate multisets and polygon
topology are checked; no arbitrary geometry change is accepted.

The server comparison is restricted to WMS 1.1.1 `GetMap`, one mapped layer,
default packaged style, PNG 512×512, EPSG:4326 and extent 0/0/4/4. It does not
accept `MAP`, external `SLD`, `SLD_BODY`, extra/duplicate parameters or a caller
renderer override. Native catalog decisions and approved asset hashes are
checked on new requests at gateway and engine boundaries; no positive policy
cache is used. Other OGC/output/admin paths and writes deny.

This is a synthetic Linux/offscreen P0 profile. Windows, physical-display UX,
general providers/fonts/CRSs, all T-CARTO-01 cases, complete publication jobs and
release acceptance remain required later work. The supporting GeoNode/Java and
package tests are not substitutes for the recorded actual render/HTTP journey.
