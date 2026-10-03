# FND-05: owned desktop packaging and two renderer paths

Status: implementation/test review pending. Task: [FND-05](https://github.com/aloerch/ambisgis-qgis-plugin/issues/1).
This is the P0 comparison spike, not the complete publishing wizard, durable
publication saga, installation, Windows acceptance or full T-CARTO-01 matrix.

Keep the existing native GeoNode catalog as the only user/token/group/resource
permission authority. Keep rendering inside the owned QGIS and GeoServer builds.
The desktop module produces a bounded copy package and an explicit capability
report. A server-owned resource binding selects a renderer behind one `/map`
entry point; a caller cannot supply a project filename, external style URL,
alternate dataset, arbitrary expression or engine administration operation.

The representative profile includes categorized point markers, simple point,
line and polygon symbols, an expression label, and a one-band grayscale raster.
QGIS's own SLD exporter rejects `upper("label")`; that case selects QGIS Server.
The raster currently also selects QGIS Server. GeoServer raster translation is
not claimed. Unsupported provider, expression, effect, join/subset, temporal,
layout and macro cases produce diagnostics instead of a silently changed map.

The clean export reconstructs providers and explicitly tested renderer/label
state, preserves copied asset bytes, records hashes/lengths/media types and the
required retained font identity, and serializes QML plus supported native SLD.
It does not execute imported project macros or package desktop forms/plugins.
The native empty project style library is removed using the owned QGIS API;
actual nonempty attachments are rejected. GDAL-generated raster statistics are
retained with a constrained XML grammar. Uploaded ZIP members are checked in
memory, without extracting caller paths. The serving fixture consumes approved
immutable copies, not arbitrary third-party project uploads.

## Primary-source comparison

The following is a documentation/source-interface comparison, not a claim that
G3W-SUITE or Lizmap was installed or benchmarked here. Sources were read on
2026-10-03; their current documentation paths can evolve.

| Approach | Existing workflow and useful capability | Authority fit for AmbisGIS |
|---|---|---|
| G3W-SUITE | Its documented composition includes QGIS project publication, an administrative backend, client and server components. The administration workflow manages project groups and access permissions. | It could reduce QGIS-focused viewer/administration work, but adopting its project/ACL administration wholesale would add another mutable authority beside the accepted catalog. Reuse would need source ownership and a deliberate replacement/adaptation plan. |
| Lizmap | Its desktop configuration and project workflow preserve QGIS-authored maps. Documented groups govern repository/project/layer access, OGC access, editing and user filtering. | Useful publishing/UX patterns, but its own rights and repository model would still need to be replaced by the accepted catalog and native managed-edit API. A documented editing feature is not evidence of AmbisGIS branch semantics. |
| Owned adapters in this spike | Native QGIS project/SLD export, native QGIS Server layer-access callbacks and a mandatory GeoServer servlet boundary. Both ask the existing catalog for each new map request. | Keeps a single authority and permits source changes in owned modules. Requires implementing the later durable publish/activation, broader output/cache authorization and UI tasks. |

Sources: [G3W composition](https://g3w-suite.readthedocs.io/en/latest/index.html),
[G3W project administration](https://g3w-suite.readthedocs.io/en/latest/g3wsuite_administration.html),
[Lizmap architecture/workflow](https://docs.lizmap.com/current/en/introduction.html),
[Lizmap rights](https://docs.lizmap.com/current/en/admin/users-groups.html),
[Lizmap project configuration](https://docs.lizmap.com/current/en/publish/configuration/project.html).
The authority-fit judgments in the final column are architectural inferences
from those documented workflows and AmbisGIS chapters 00/06/11, not assertions
of a security defect in either project. No third-party source is imported and
no license or trademark permission is inferred from this comparison.

## Chosen owned extension interfaces

Desktop uses `QgsProject`, native layer renderers/labeling, `saveNamedStyle`,
`saveSldStyle` and retained OGR/GDAL providers. Packaging recreates a clean
project from the analyzed subset. QGIS Server uses the owned `QgsServer`
library and `QgsAccessControlFilter.layerPermissions`/`allowToEdit`; its native
dispatch is sequential because the API is not thread safe. These interfaces
are documented in the [QGIS 3.44 server cookbook](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/server.html)
and were exercised against source-owned binaries. They do not make future
upstream hooks or plugin-only access to an externally maintained engine a
product dependency. Core refactoring remains permitted.

The companion platform branch owns the permanent Python/Java enforcement
sources. The old FND-03 WFS parser remains separate and unchanged. Map requests
use a finite WMS 1.1.1 GetMap profile: one mapped layer, empty default style,
EPSG:4326, extent 0/0/4/4, PNG at 512². Each engine also checks the exact approved
data/style/project bytes; a changed asset denies. Raw admin, external style,
project-path injection, mixed layers, unsupported methods and other outputs
deny. This profile does not authorize arbitrary WMS, feature-info, legend,
tile/cache, download, print or notebook paths.

## Remaining product work

The tested target is Linux/Qt5/Python3.13/QGIS3.44 with controlled offscreen
rendering and retained fonts. Windows is untested and remains a separate
required desktop target. No macOS support is claimed. All server processes use
the existing loopback supervisor; its documented PostgreSQL exception remains.
This is not an Internet-facing deployment or a hostile-file sandbox certification.

Further tasks retain the original requirements for UI sign-in, server-side
registered references, schema/CRS breadth, font/asset licensing, all output types,
durable jobs/private staging, idempotency/cancellation, safe activation,
overwrite/rollback, branch editing and broader authorization/abuse testing.
No durable saga, cache safety or release acceptance follows merely from this
comparison, a package ZIP, screenshots or a merged PR.
