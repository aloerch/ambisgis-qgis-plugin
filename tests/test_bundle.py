import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from ambisgis_publishing.bundle import inspect_bundle, write_bundle
from ambisgis_publishing.analyzer import geojson_profile


class BundleGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def package(self):
        source = self.root / 'source'; source.mkdir()
        (source / 'project.qgs').write_text('<qgis/>')
        return write_bundle(source, self.root / 'package.zip', {'layers': []})

    def altered(self, change):
        self.package()
        with zipfile.ZipFile(self.root / 'package.zip') as z:
            contents = {i.filename: z.read(i) for i in z.infolist()}
        change(contents)
        target = self.root / 'altered.zip'
        with zipfile.ZipFile(target, 'w') as z:
            for name, data in contents.items(): z.writestr(name, data)
        return target

    def test_hash_tamper_rejected(self):
        path = self.altered(lambda data: data.update({'project.qgs': b'<qgis bad="true"/>'}))
        with self.assertRaises(ValueError): inspect_bundle(path)

    def test_unlisted_file_rejected(self):
        path = self.altered(lambda data: data.update({'extra.py': b'code'}))
        with self.assertRaises(ValueError): inspect_bundle(path)

    def test_traversal_rejected(self):
        path = self.altered(lambda data: data.update({'../escape': b'bad'}))
        with self.assertRaises(ValueError): inspect_bundle(path)

    def test_duplicate_member_rejected(self):
        self.package(); path = self.root / 'package.zip'
        with zipfile.ZipFile(path, 'a') as z: z.writestr('project.qgs', '<qgis/>')
        with self.assertRaises(ValueError): inspect_bundle(path)

    def test_source_symlink_rejected(self):
        source = self.root / 'source'; source.mkdir()
        (source / 'project.qgs').symlink_to('/etc/hosts')
        with self.assertRaises(ValueError): write_bundle(source, self.root / 'bad.zip', {})

    def test_existing_destination_untouched(self):
        self.package(); path = self.root / 'package.zip'; before = path.read_bytes()
        with self.assertRaises(FileExistsError): write_bundle(self.root / 'source', path, {})
        self.assertEqual(before, path.read_bytes())

    def test_round_trip_and_no_authority_from_manifest(self):
        self.package(); manifest, contents = inspect_bundle(self.root / 'package.zip')
        self.assertEqual(set(contents), {'project.qgs'})
        self.assertEqual(manifest['schema_version'], 1)
        self.assertNotIn('policy', manifest)

    def test_compressed_bomb_rejected_before_read(self):
        path=self.root/'bomb.zip'
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('project.qgs',b'x'*1000000)
        with self.assertRaises(ValueError):inspect_bundle(path)

    def test_auxiliary_external_reference_rejected(self):
        source=self.root/'source';source.mkdir()
        (source/'project.qgs').write_text('<qgis/>')
        (source/'elevation.tif.aux.xml').write_text('<PAMDataset><SourceFilename>/etc/passwd</SourceFilename></PAMDataset>')
        with self.assertRaises(ValueError):write_bundle(source,self.root/'bad.zip',{})

    def test_renamed_vrt_rejected_before_packaging(self):
        path=self.root/'data.geojson';path.write_text('<OGRVRTDataSource><OGRVRTLayer name="secret"/></OGRVRTDataSource>')
        with self.assertRaises(ValueError):geojson_profile(path)

    def test_geojson_coordinate_and_foreign_member_rejection(self):
        path=self.root/'data.geojson'
        valid={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'label':'Å'},
               'geometry':{'type':'Point','coordinates':[1,2]}}]}
        path.write_text(json.dumps(valid));self.assertEqual(geojson_profile(path),valid)
        for coordinates in ([1,2,3],[float('nan'),2],[120,2]):
            valid['features'][0]['geometry']['coordinates']=coordinates
            path.write_text(json.dumps(valid))
            with self.assertRaises(ValueError):geojson_profile(path)
        valid['features'][0]['geometry']['coordinates']=[1,2];valid['url']='https://example.invalid/data'
        path.write_text(json.dumps(valid))
        with self.assertRaises(ValueError):geojson_profile(path)

    def test_nonfinite_numeric_properties_rejected(self):
        path=self.root/'data.geojson'
        for number in ('NaN','Infinity','-Infinity','1e400'):
            with self.subTest(number=number):
                path.write_text('{"type":"FeatureCollection","features":[{"type":"Feature",'
                    '"properties":{"amount":'+number+'},"geometry":{"type":"Point","coordinates":[1,2]}}]}')
                with self.assertRaises(ValueError):geojson_profile(path)


if __name__ == '__main__': unittest.main()
