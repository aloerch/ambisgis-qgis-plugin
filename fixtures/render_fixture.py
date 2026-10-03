"""Generate synthetic redistribution-safe styles using the actual owned PyQGIS."""
import json
from pathlib import Path
import sys

from qgis.core import (Qgis, QgsApplication, QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem, QgsFillSymbol, QgsLineSymbol, QgsMapSettings,
    QgsMapRendererParallelJob, QgsMarkerSymbol, QgsPalLayerSettings, QgsProject,
    QgsRectangle, QgsReferencedRectangle, QgsRendererCategory, QgsTextFormat,
    QgsVectorLayer, QgsVectorLayerSimpleLabeling, QgsVectorFileWriter,
    QgsRasterLayer, QgsContrastEnhancement, QgsSingleBandGrayRenderer, QgsPointXY)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QFont, QFontDatabase
from ambisgis_publishing.bundle import digest


def vector(output, name, geometry, features):
    path = output / (name + '.geojson')
    data = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'id': index, 'properties': properties,
         'geometry': {'type': geometry, 'coordinates': coordinates}}
        for index, (properties, coordinates) in enumerate(features, 1)]}
    path.write_text(json.dumps(data, sort_keys=True) + '\n')
    layer = QgsVectorLayer(str(path), name, 'ogr')
    assert layer.isValid(), name
    layer.serverProperties().setShortName(name)
    return layer


def render(layers, path):
    settings = QgsMapSettings(); settings.setLayers(layers)
    settings.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    settings.setExtent(QgsRectangle(0, 0, 4, 4)); settings.setOutputSize(QSize(512, 512))
    settings.setOutputDpi(96); settings.setBackgroundColor(QColor('white'))
    job = QgsMapRendererParallelJob(settings); job.start(); job.waitForFinished()
    assert not job.errors(), [error.message for error in job.errors()]
    image = job.renderedImage(); assert image.save(str(path), 'PNG')
    return {'sha256': digest(path.read_bytes()), 'width': image.width(), 'height': image.height()}


def main(config):
    output = Path(config['output']) / 'fixtures'; output.mkdir()
    QgsApplication.setPrefixPath(config['qgis_prefix'], True)
    app = QgsApplication([], True); app.initQgis()
    font_id = QFontDatabase.addApplicationFont(config['font_file']); assert font_id >= 0
    family = QFontDatabase.applicationFontFamilies(font_id)[0]
    points = [({'id': 1, 'label': 'Alpha Å', 'kind': 'home', 'value': 5}, [1, 1]),
              ({'id': 2, 'label': 'Beta', 'kind': 'school', 'value': 12}, [3, 1]),
              ({'id': 3, 'label': 'Gamma', 'kind': 'home', 'value': 20}, [2, 3])]
    public = vector(output, 'public_points', 'Point', points)
    categories = []
    for value, color in [('home', '#dc141e'), ('school', '#143ce6')]:
        symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': color,
                                              'outline_style': 'no', 'size': '5'})
        categories.append(QgsRendererCategory(value, symbol, value))
    public.setRenderer(QgsCategorizedSymbolRenderer('kind', categories))
    private = vector(output, 'private_points', 'Point', points)
    private.renderer().setSymbol(QgsMarkerSymbol.createSimple(
        {'name': 'square', 'color': '#008040', 'outline_style': 'no', 'size': '4'}))
    rich = vector(output, 'rich_points', 'Point', points)
    rich.setRenderer(private.renderer().clone())
    label = QgsPalLayerSettings(); label.fieldName = 'upper("label")'; label.isExpression = True
    fmt = QgsTextFormat(); fmt.setFont(QFont(family)); fmt.setSize(12); fmt.setColor(QColor('#202020'))
    label.setFormat(fmt); rich.setLabeling(QgsVectorLayerSimpleLabeling(label)); rich.setLabelsEnabled(True)
    roads = vector(output, 'group_points', 'LineString', [
        ({'id': 1, 'label': 'Road', 'kind': 'road', 'value': 1}, [[.5, 2], [3.5, 2]])])
    roads.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color': '#e08000', 'line_width': '1.2'}))
    parcels = vector(output, 'parcels', 'Polygon', [
        ({'id': 1, 'label': 'Parcel', 'kind': 'parcel', 'value': 1}, [[[.5, .5], [1.5, .5], [1.5, 1.5], [.5, 1.5], [.5, .5]]])])
    parcels.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '#8060c0', 'outline_style': 'no'}))
    from fixture import make_data
    raster_data = output / 'raster'; raster_data.mkdir(); make_data(raster_data, config['gdal_library'])
    elevation = QgsRasterLayer(str(raster_data / 'known.tif'), 'elevation', 'gdal'); assert elevation.isValid()
    elevation.serverProperties().setShortName('elevation')
    grayscale = QgsSingleBandGrayRenderer(elevation.dataProvider(), 1)
    contrast = QgsContrastEnhancement(elevation.dataProvider().dataType(1))
    contrast.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
    contrast.setMinimumValue(0); contrast.setMaximumValue(255); grayscale.setContrastEnhancement(contrast)
    elevation.setRenderer(grayscale)
    project = QgsProject.instance(); project.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    project.setTitle('Synthetic FND05 renderer comparison')
    layers = [public, private, roads, parcels, rich, elevation]
    for layer in layers: project.addMapLayer(layer)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(QgsRectangle(0, 0, 4, 4), project.crs()))
    project.writeEntry('WMSServiceCapabilities', '/', True)
    project.writeEntry('WMSCrsList', '/', ['EPSG:4326'])
    project.setFileName(str(output / 'authoring.qgs')); assert project.write()
    results = {}
    for layer in layers:
        message, ok = layer.saveNamedStyle(str(output / (layer.name() + '.qml'))); assert ok, message
        if isinstance(layer, QgsRasterLayer):
            results[layer.name()] = {'width':layer.width(),'height':layer.height(),
                                     'render':render([layer],output/(layer.name()+'.png'))}
            continue
        message, ok = layer.saveSldStyle(str(output / (layer.name() + '.sld')))
        assert ok == (layer.name() != 'rich_points'), message
        sld = {'supported': ok, 'diagnostic': message}
        target = output / 'geoserver' / layer.name(); target.mkdir(parents=True)
        options = QgsVectorFileWriter.SaveVectorOptions(); options.driverName = 'ESRI Shapefile'
        result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(target / (layer.name() + '.shp')),
                                                         project.transformContext(), options)
        assert result[0] == QgsVectorFileWriter.NoError, result
        interchange=QgsVectorLayer(str(target/(layer.name()+'.shp')),'interchange','ogr')
        assert interchange.isValid()
        expected_rows=[(f.attributes(),f.geometry().asWkt()) for f in layer.getFeatures()]
        actual_rows=[]; single_part_promotions=0; ring_order_changes=0
        source_features=list(layer.getFeatures())
        for index,feature in enumerate(interchange.getFeatures()):
            geometry=feature.geometry()
            # OGR exposes Shapefile lines/polygons as multi geometries. Require
            # exactly one part, then compare every original coordinate and value.
            if geometry.isMultipart():
                assert len(geometry.asGeometryCollection())==1
                assert geometry.convertToSingleType();single_part_promotions+=1
            original_geometry=source_features[index].geometry()
            if layer.name()=='parcels' and geometry.asWkt()!=original_geometry.asWkt():
                # Shapefile's clockwise ring convention differs from GeoJSON.
                # Require equal topology and the complete coordinate multiset.
                assert geometry.isGeosEqual(original_geometry)
                assert sorted((v.x(),v.y()) for v in geometry.vertices())==sorted((v.x(),v.y()) for v in original_geometry.vertices())
                ring_order_changes+=1
                geometry=original_geometry
            actual_rows.append((feature.attributes(),geometry.asWkt()))
        assert actual_rows==expected_rows, (layer.name(),actual_rows,expected_rows)
        results[layer.name()] = {'features': layer.featureCount(), 'geometry_type': layer.geometryType(),
                                'shapefile_attributes_coordinates_equal':True,
                                'shapefile_single_part_promotions':single_part_promotions,
                                'shapefile_polygon_ring_order_changes':ring_order_changes,
                                'sld': sld, 'render': render([layer], output / (layer.name() + '.png'))}
    report = {'qgis_version': Qgis.QGIS_VERSION, 'qt_family': family, 'layers': results,
              'combined': render(layers, output / 'combined.png'), 'status': 'passed'}
    from ambisgis_publishing.analyzer import analyze, package
    analysis, manifest = package(project, output, output / 'packaged', font_family=family,
                                 font_sha256=digest(Path(config['font_file']).read_bytes()))
    assert analysis['default_renderer'] == 'qgis-server'
    assert all(row['geoserver'] == (row['layer'] not in ('rich_points','elevation')) for row in analysis['layers'])
    packaged = QgsProject(); assert packaged.read(str(output / 'packaged/content/project.qgs'))
    comparisons = {}
    for layer in layers:
        reopened = packaged.mapLayersByName(layer.name())[0]
        assert reopened.isValid()
        if isinstance(layer, QgsRasterLayer):
            assert (reopened.width(),reopened.height())==(16,16)
            for x,y,value in ((.5,3.5,40),(3.5,3.5,90),(.5,.5,150),(3.5,.5,210)):
                actual,ok=reopened.dataProvider().sample(QgsPointXY(x,y),1);assert ok and actual==value
        else:
            assert reopened.featureCount() == layer.featureCount()
            original = [(f.attributes(), f.geometry().asWkt()) for f in layer.getFeatures()]
            copied = [(f.attributes(), f.geometry().asWkt()) for f in reopened.getFeatures()]
            assert original == copied
        actual = render([reopened], output / ('packaged-' + layer.name() + '.png'))
        assert actual['sha256'] == results[layer.name()]['render']['sha256']
        comparisons[layer.name()] = {'semantic_data_equal': True, 'render_identical': True}
    packaged.clear()
    # Negative analyzer cases use actual native objects. No network provider is opened.
    rejected = QgsProject(); unsupported = QgsVectorLayer('Point?crs=EPSG:4326', 'memory_layer', 'memory')
    rejected.addMapLayer(unsupported)
    negative = analyze(rejected, output, font_family=family)
    assert not negative['all_publishable']
    rejected.clear()
    saved = rich.labeling().clone()
    unsafe = label; unsafe.fieldName = 'eval("label")'
    rich.setLabeling(QgsVectorLayerSimpleLabeling(unsafe))
    dynamic = analyze(project, output, font_family=family)
    assert not dynamic['all_publishable']
    rich.setLabeling(saved)
    negatives = {'memory_provider_rejected': True, 'unapproved_expression_rejected': True}
    project.writeEntry('Macros','pythonCode','raise RuntimeError("must never run")')
    assert not analyze(project,output,font_family=family)['all_publishable']
    project.removeEntry('Macros','pythonCode');negatives['macro_rejected']=True
    attachment=project.createAttachedFile('unapproved.txt');Path(attachment).write_text('Synthetic attachment')
    assert not analyze(project,output,font_family=family)['all_publishable']
    project.removeAttachedFile(attachment);negatives['authored_attachment_rejected']=True
    assert public.setSubsetString('"id"=1')
    assert not analyze(project,output,font_family=family)['all_publishable']
    public.setSubsetString('');negatives['subset_not_silently_discarded']=True
    public.setCrs(QgsCoordinateReferenceSystem('EPSG:2230'))
    assert not analyze(project,output,font_family=family)['all_publishable']
    public.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'));negatives['unsupported_crs_rejected']=True
    assert not analyze(project,output/'other-root',font_family=family)['all_publishable']
    negatives['outside_source_root_rejected']=True
    assert not analyze(project,output,font_family='unavailable-font')['all_publishable']
    negatives['unavailable_font_rejected']=True
    from qgis.core import QgsSvgMarkerSymbolLayer, QgsSingleSymbolRenderer
    old=public.renderer().clone()
    symbol=QgsMarkerSymbol();symbol.changeSymbolLayer(0,QgsSvgMarkerSymbolLayer(str(output/'unapproved.svg')))
    public.setRenderer(QgsSingleSymbolRenderer(symbol))
    assert not analyze(project,output,font_family=family)['all_publishable']
    public.setRenderer(old);negatives['external_svg_rejected']=True
    from qgis.core import QgsProperty, QgsSymbol
    saved_symbol=private.renderer().symbol().clone()
    private.renderer().symbol().dataDefinedProperties().setProperty(QgsSymbol.Property.Opacity,QgsProperty.fromExpression('"value"'))
    assert not analyze(project,output,font_family=family)['all_publishable']
    private.renderer().setSymbol(saved_symbol);negatives['symbol_expression_rejected']=True
    source_path=Path(public.source());original_bytes=source_path.read_bytes()
    try:
        for name,value in (('nan',float('nan')),('positive_infinity',float('inf')),('negative_infinity',float('-inf'))):
            malformed=json.loads(original_bytes);malformed['features'][0]['properties']['value']=value
            source_path.write_text(json.dumps(malformed))
            assert not analyze(project,output,font_family=family)['all_publishable']
            negatives[name+'_property_rejected']=True
    finally:source_path.write_bytes(original_bytes)
    report.update(analysis=analysis, package_roundtrip=comparisons,
                  negative_analyzer=negatives)
    # Assert selected native/Qt/provider origins in the real process, not just environment paths.
    from runtime_common import loaded_origins, provider_origins, python_origins
    report.update(loaded_origins=loaded_origins(config), provider_origins=provider_origins(config),
                  python_origins=python_origins(config))
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    project.clear(); del layers, public, private, roads, parcels, rich, elevation, packaged, rejected, unsupported, reopened, interchange
    import gc
    gc.collect()
    app.exitQgis()


if __name__ == '__main__': main(json.loads(Path(sys.argv[1]).read_text()))
