"""Explicit finite copy/style profile for the FND05 prototype.

Desktop-authored layers are analyzed before reconstructing a clean server
project. Arbitrary uploaded project files are not opened by this module.
"""
import json
from pathlib import Path
import re
import shutil
import math

from .bundle import MAX_BYTES, digest, write_bundle


def geojson_profile(path):
    """Reject renamed VRT/remote-provider containers before copying to a server."""
    if path.stat().st_size > MAX_BYTES: raise ValueError('source exceeds package limit')
    def invalid_constant(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    value=json.loads(path.read_text(), parse_constant=invalid_constant)
    if (not isinstance(value,dict) or set(value)-{'type','name','features'} or value.get('type')!='FeatureCollection'
            or not isinstance(value.get('features'),list) or not 0<len(value['features'])<=10000):
        raise ValueError('source is outside the bounded GeoJSON profile')
    depths={'Point':1,'LineString':2,'Polygon':3}
    def coordinates(value,depth):
        if not isinstance(value,list) or not value:raise ValueError('invalid coordinate array')
        if depth==1:
            if len(value)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=4 for n in value):
                raise ValueError('coordinates exceed the fixed 2D comparison extent')
        else:
            for child in value:coordinates(child,depth-1)
    for feature in value['features']:
        if not isinstance(feature,dict) or set(feature)-{'type','id','properties','geometry'} or feature.get('type')!='Feature':
            raise ValueError('invalid GeoJSON feature')
        props=feature.get('properties')
        if not isinstance(props,dict) or any(type(v) not in (str,int,float,bool,type(None)) for v in props.values()):
            raise ValueError('unsupported property values')
        if any(isinstance(v,float) and not math.isfinite(v) for v in props.values()):
            raise ValueError('nonfinite numeric property')
        geometry=feature.get('geometry')
        if not isinstance(geometry,dict) or set(geometry)!={'type','coordinates'} or geometry.get('type') not in depths:
            raise ValueError('unsupported geometry')
        coordinates(geometry['coordinates'],depths[geometry['type']])
    return value


def analyze(project, source_root, *, font_family):
    from qgis.core import QgsVectorLayer, QgsRasterLayer, Qgis
    from qgis.PyQt.QtGui import QPainter
    root = Path(source_root).resolve()
    project_diagnostics = []
    if project.readEntry('Macros', 'pythonCode', '')[0]:
        project_diagnostics.append({'code':'PROJECT_MACROS','message':'Project macros are not executed or packaged.'})
    if project.layoutManager().layouts():
        project_diagnostics.append({'code':'LAYOUT_PROFILE','message':'Layouts require a separate publication profile; this profile serves dynamic maps.'})
    library = project.styleSettings().projectStyle()
    counts = ('symbolCount','colorRampCount','textFormatCount','legendPatchShapesCount','symbol3DCount','labelSettingsCount')
    empty_library = library and not any(getattr(library,method)() for method in counts)
    ignored = {library.fileName()} if empty_library else set()
    if set(project.attachedFiles())-ignored or project.styleSettings().styleDatabasePaths():
        project_diagnostics.append({'code':'PROJECT_ATTACHMENTS','message':'Authored attachments and external style libraries require explicit packaging support.'})
    rows = []
    for layer in project.mapLayers().values():
        diagnostics = []
        def note(code, message, *, error=True):
            diagnostics.append({'code': code, 'message': message, 'severity': 'error' if error else 'renderer'})
        name = layer.name()
        if not re.fullmatch(r'[a-z][a-z_]{0,63}', name): note('LAYER_NAME', 'Use a stable ASCII layer reference for this profile.')
        if not layer.isValid(): note('INVALID_LAYER', 'Source layer cannot be read.')
        if layer.crs().authid() != 'EPSG:4326': note('CRS_PROFILE', 'This comparison profile supports EPSG:4326; no hidden reprojection.')
        if isinstance(layer, QgsRasterLayer) and layer.providerType() == 'gdal':
            source = Path(layer.source())
            if (source.suffix.lower() != '.tif' or not source.is_file() or source.is_symlink()
                    or not source.resolve().is_relative_to(root) or any(p.is_symlink() for p in source.parents)):
                note('SOURCE_BOUNDARY', 'Raster copy requires a regular local GeoTIFF inside the selected source root.')
            elif source.stat().st_size>MAX_BYTES:
                note('SOURCE_SIZE','Raster exceeds the package size limit.')
            elif source.read_bytes()[:4] not in (b'II*\x00', b'MM\x00*'):
                note('RASTER_SIGNATURE', 'Raster contents are not the tested TIFF format.')
            if layer.bandCount() != 1 or layer.renderer().type() != 'singlebandgray':
                note('RASTER_STYLE', 'Only the tested one-band grayscale raster profile is supported.')
            elif (layer.dataProvider().dataType(1) != Qgis.DataType.Byte or layer.renderer().opacity() != 1
                    or layer.blendMode() != QPainter.CompositionMode_SourceOver):
                note('RASTER_PROFILE', 'Only opaque Byte grayscale data is tested in this profile.')
            note('RASTER_TRANSLATION', 'This prototype retains the QGIS raster renderer; GeoServer raster translation is not claimed.', error=False)
            errors = any(row['severity'] == 'error' for row in diagnostics)
            rows.append({'layer':name,'provider':'gdal','crs':layer.crs().authid(),
                         'width':layer.width(),'height':layer.height(),'bands':layer.bandCount(),
                         'renderer':layer.renderer().type(),'diagnostics':diagnostics,
                         'qgis_server':not errors,'geoserver':False})
            continue
        if not isinstance(layer, QgsVectorLayer) or layer.providerType() != 'ogr':
            note('PROVIDER_PROFILE', 'Copy supports local GeoJSON vectors only; other providers require a reviewed profile or registered source.')
            rows.append({'layer': name, 'provider': layer.providerType(), 'diagnostics': diagnostics,
                         'qgis_server': False, 'geoserver': False}); continue
        source = Path(layer.source())
        if (source.suffix.lower() != '.geojson' or not source.is_file() or source.is_symlink()
                or not source.resolve().is_relative_to(root) or any(p.is_symlink() for p in source.parents)):
            note('SOURCE_BOUNDARY', 'Source must be a regular GeoJSON inside the selected copy root, with no URL, credentials, or provider options.')
        else:
            try: geojson_profile(source)
            except (ValueError,OSError,RecursionError,UnicodeError):
                note('GEOJSON_PROFILE','Expected bounded 2D Point/LineString/Polygon GeoJSON in extent 0–4; other content must use another reviewed profile.')
        renderer = layer.renderer()
        if layer.subsetString() or layer.vectorJoins() or layer.auxiliaryLayer():
            note('DEPENDENT_DATA', 'Subset filters, joins and auxiliary layers require explicit materialization; they are not silently discarded.')
        if layer.hasScaleBasedVisibility() or layer.temporalProperties().isActive():
            note('VISIBILITY_PROFILE', 'Scale/temporal rules require another reviewed profile.')
        if renderer.type() not in ('singleSymbol', 'categorizedSymbol'):
            note('RENDERER_PROFILE', 'Renderer is outside the tested simple/categorized subset.')
        symbols = []
        if renderer.type() == 'singleSymbol': symbols = [renderer.symbol()]
        elif renderer.type() == 'categorizedSymbol':
            # SIP returns category value objects which own their symbol pointers.
            # Keep them alive while inspecting those borrowed native pointers.
            categories = renderer.categories()
            symbols = [category.symbol() for category in categories]
            if renderer.classAttribute() not in [field.name() for field in layer.fields()]:
                note('CATEGORY_EXPRESSION', 'Categorization expressions are outside this profile.')
        for symbol in symbols:
            if symbol.hasDataDefinedProperties(): note('SYMBOL_DYNAMIC', 'Symbol-level data-defined properties require another reviewed profile.')
            if symbol.symbolLayerCount() != 1 or symbol.opacity() != 1:
                note('SYMBOL_COMPOSITION', 'Only one opaque symbol layer is tested by this profile.')
            for index in range(symbol.symbolLayerCount()):
                part = symbol.symbolLayer(index)
                if part.layerType() not in ('SimpleMarker', 'SimpleLine', 'SimpleFill'):
                    note('SYMBOL_PROFILE', 'External SVG, geometry generators and plugin symbol layers require another reviewed profile.')
                properties = part.properties()
                if part.layerType() == 'SimpleMarker' and properties.get('name') not in ('circle','square'):
                    note('MARKER_SHAPE', 'Only circle and square markers are tested by this profile.')
                if part.hasDataDefinedProperties(): note('DATA_DEFINED', 'Data-defined symbol properties are not silently flattened.')
                effect = part.paintEffect()
                if effect and effect.enabled(): note('SYMBOL_EFFECT', 'Enabled symbol effects require another reviewed profile.')
        if layer.blendMode() != QPainter.CompositionMode_SourceOver or layer.opacity() != 1:
            note('BLEND_MODE', 'Blend/opacity effects are not included in this finite comparison profile.')
        if layer.featureBlendMode() != QPainter.CompositionMode_SourceOver:
            note('FEATURE_BLEND', 'Feature blend modes require another reviewed profile.')
        if layer.labelsEnabled():
            note('LABEL_TRANSLATION', 'Label fidelity uses QGIS Server; GeoServer label translation is outside this tested subset.', error=False)
            labeling = layer.labeling()
            if labeling.type() != 'simple': note('LABEL_RULES', 'Rule-based labeling is outside this profile.')
            else:
                settings = labeling.settings()
                text_format = settings.format()  # Keep SIP value owner alive for borrowed property collections.
                if settings.isExpression:
                    if settings.fieldName != 'upper("label")': note('LABEL_EXPRESSION', 'Only the tested upper(label) expression is allowed by this profile.')
                    note('SLD_LABEL_EXPRESSION', 'Native QGIS SLD export rejects this expression; choose QGIS Server.', error=False)
                elif settings.fieldName not in [field.name() for field in layer.fields()]: note('LABEL_FIELD', 'Label field is missing.')
                if text_format.font().family() != font_family: note('FONT_DEPENDENCY', 'Label font is not the pinned runtime font.')
                if text_format.allowHtmlFormatting() or text_format.background().enabled():
                    note('LABEL_ASSETS', 'HTML labels and label backgrounds are outside the asset-free text profile.')
                if (settings.dataDefinedProperties().hasActiveProperties() or
                        text_format.dataDefinedProperties().hasActiveProperties()):
                    note('LABEL_DYNAMIC', 'Dynamic label properties are outside this profile.')
        fields = [field.name() for field in layer.fields()]
        if len(set(name.lower() for name in fields)) != len(fields) or any(len(name)>10 for name in fields):
            note('SHAPEFILE_FIELD_NAMES', 'The GeoServer comparison import cannot preserve these Shapefile field names; use QGIS Server.', error=False)
        if any(isinstance(value,str) and len(value.encode('utf-8'))>254 for feature in layer.getFeatures() for value in feature.attributes()):
            note('SHAPEFILE_TEXT_WIDTH', 'The GeoServer comparison import cannot preserve this UTF-8 attribute width; use QGIS Server.', error=False)
        errors = any(row['severity'] == 'error' for row in diagnostics)
        rows.append({'layer': name, 'provider': layer.providerType(), 'crs': layer.crs().authid(),
                     'fields': [{'name': field.name(), 'type': field.typeName()} for field in layer.fields()],
                     'feature_count': layer.featureCount(), 'renderer': renderer.type(),
                     'diagnostics': diagnostics, 'qgis_server': not errors,
                     'geoserver': not errors and not any(row['severity'] == 'renderer' for row in diagnostics)})
    if len({row['layer'] for row in rows}) != len(rows): raise ValueError('duplicate layer references')
    return {'schema_version': 1, 'profile': 'fnd05-geographic-copy-v1', 'layers': sorted(rows, key=lambda row: row['layer']),
            'project_diagnostics': project_diagnostics,
            'all_publishable': bool(rows) and not project_diagnostics and all(row['qgis_server'] for row in rows),
            'default_renderer': 'geoserver' if rows and all(row['geoserver'] for row in rows) else 'qgis-server'}


def package(project, source_root, destination, *, font_family, font_sha256):
    from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer, QgsCoordinateReferenceSystem,
                           QgsRectangle, QgsReferencedRectangle, Qgis)
    report = analyze(project, source_root, font_family=font_family)
    if not report['all_publishable']: raise ValueError('publication analyzer rejected one or more layers')
    destination = Path(destination); destination.mkdir(mode=0o700)
    root = destination / 'content'; root.mkdir(mode=0o700)
    assets = root / 'assets'; assets.mkdir()
    styles = root / 'styles'; styles.mkdir()
    clean = QgsProject(); clean.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    # A fresh QgsProject creates an empty style-library attachment. All tested
    # symbols are embedded in layer renderers; remove this unused library through
    # the native API, never strip an author's nonempty attachment implicitly.
    library = clean.styleSettings().projectStyle()
    if library:
        if any(getattr(library,method)() for method in ('symbolCount','colorRampCount','textFormatCount','legendPatchShapesCount','symbol3DCount','labelSettingsCount')):
            raise ValueError('unexpected new-project style library')
        attachment_path = library.fileName()
        clean.styleSettings().removeProjectStyle(); clean.removeAttachedFile(attachment_path)
    clean.setTitle('AmbisGIS synthetic publication')
    clean.writeEntry('WMSServiceCapabilities', '/', True)
    clean.writeEntry('WMSCrsList', '/', ['EPSG:4326'])
    clean.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(QgsRectangle(0, 0, 4, 4), clean.crs()))
    try:
        for row in report['layers']:
            layer = project.mapLayersByName(row['layer'])[0]
            raster = row['provider'] == 'gdal'
            target = assets / (row['layer'] + ('.tif' if raster else '.geojson')); shutil.copyfile(layer.source(), target)
            exported = QgsRasterLayer(str(target), row['layer'], 'gdal') if raster else QgsVectorLayer(str(target), row['layer'], 'ogr')
            exported.setRenderer(layer.renderer().clone())
            if not raster and layer.labelsEnabled():
                exported.setLabeling(layer.labeling().clone()); exported.setLabelsEnabled(True)
            exported.serverProperties().setShortName(row['layer']); clean.addMapLayer(exported)
            message, ok = exported.saveNamedStyle(str(styles / (row['layer'] + '.qml')))
            if not ok: raise ValueError('native QML export failed')
            if row['geoserver']:
                message, ok = exported.saveSldStyle(str(styles / (row['layer'] + '.sld')))
                if not ok: raise ValueError('native SLD export failed instead of satisfying analyzer profile')
        clean.setFileName(str(root / 'project.qgs'))
        if not clean.write(): raise ValueError('clean project serialization failed')
    finally: clean.clear()
    # An empty sidecar is disposable; any actual attachment remains a hard error.
    attachment = root / 'project_attachments.zip'
    if attachment.exists():
        import zipfile
        with zipfile.ZipFile(attachment) as archive:
            if archive.namelist(): raise ValueError('unexpected project attachment')
        attachment.unlink()
    metadata = {'analysis': report, 'qgis_version': Qgis.QGIS_VERSION,
                'runtime_font': {'family': font_family, 'sha256': font_sha256,
                    'declaration': 'Required retained QGIS Vera font; not embedded or relicensed by this package.'}}
    manifest = write_bundle(root, destination / 'publication.zip', metadata)
    (destination / 'analysis.json').write_text(json.dumps(report, indent=2) + '\n')
    return report, manifest
