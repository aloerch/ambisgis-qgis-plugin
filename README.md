# AmbisGIS desktop publication prototype

FND-05 implements native QGIS style analysis and bounded copy packages, with a
companion platform fixture for catalog-authorized GeoServer/QGIS Server maps.
This repository owns desktop packaging and synthetic fixtures. Permanent engine
enforcement lives in the owned platform repository. It is not an installable
publishing wizard or released desktop product.

Read the [capability profile](docs/capability-profile.md) and
[renderer decision/G3W–Lizmap comparison](docs/decisions/0001-renderer-comparison.md).
The source-owned QGIS 3.44/Qt5/Python3.13 family is exercised on Linux offscreen;
Windows and the broader desktop publication requirements remain open.

Run package/input guard tests with:

```sh
python3 -m unittest discover -s tests -v
```

These unit tests do not establish GIS acceptance. The native fixture
`fixtures/render_fixture.py` must run under an explicit owned PyQGIS runtime
using platform `build-support/renderer/qgis_probe.py`; its fresh output contains
the original authoring project, native renders, interchange files, a copied
publication package and actual comparison results. The platform's native
`build-support/geonode/run.py --catalog-policy --renderer-fixture …` supplies the
real identity/authorization/rendering journey. Exact commands, artifact/source
identities and retained evidence are recorded with the completed task review.

The [safe native receipt](verification/native-renderer.json) binds the executed
source hashes and exact runtime inputs. The completed run produced 152 real
HTTP checks (49 allowed maps and 103 denials), with 49 PNG outputs compared to
native authoring renders. [Actual fixture images](docs/rendered-fixture/README.md)
are retained for inspection; they are not generated mockups or UI screenshots.

The `bundle-guards` workflow checks the stdlib package guards on exact owned
source. Native GIS acceptance remains a separately reviewed, evidence-bound
check; hosted unit-test success alone does not establish it.
