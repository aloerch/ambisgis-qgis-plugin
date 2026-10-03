"""Bounded content package. Its manifest never grants authorization.

Validation returns bytes; it never extracts uploaded paths onto the filesystem.
The server separately validates project semantics before using a package.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
import xml.etree.ElementTree as ET

MAX_BYTES = 32 * 1024 * 1024
MAX_FILES = 128
MEDIA = {'.qgs': 'application/xml', '.qml': 'application/xml', '.sld': 'application/xml',
         '.geojson': 'application/geo+json', '.tif': 'image/tiff', '.xml':'application/xml'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_media(name, data):
    suffix = Path(name).suffix
    if suffix not in MEDIA: raise ValueError('unsupported package member')
    if suffix == '.xml':
        # GDAL's generated PAM statistics are material package dependencies. No
        # arbitrary auxiliary XML paths, projection overrides, or external links.
        if not name.endswith('.tif.aux.xml') or len(data) > 8192 or b'<!' in data:
            raise ValueError('unsupported auxiliary XML')
        try:
            root=ET.fromstring(data)
            if root.tag!='PAMDataset' or root.attrib or len(root)!=1: raise ValueError('invalid raster metadata')
            band=root[0]
            if band.tag!='PAMRasterBand' or band.attrib!={'band':'1'} or len(band)!=1: raise ValueError('invalid raster band metadata')
            metadata=band[0]
            if metadata.tag!='Metadata' or metadata.attrib: raise ValueError('invalid raster statistics')
            allowed={'STATISTICS_MINIMUM','STATISTICS_MAXIMUM','STATISTICS_MEAN','STATISTICS_STDDEV','STATISTICS_VALID_PERCENT'}
            keys=[]
            for entry in metadata:
                if (entry.tag!='MDI' or set(entry.attrib)!={'key'} or len(entry)
                        or entry.get('key') not in allowed or not re.fullmatch(r'-?\d+(\.\d+)?',entry.text or '')):
                    raise ValueError('unsupported raster statistics')
                keys.append(entry.get('key'))
            if len(keys)!=len(set(keys)): raise ValueError('duplicate raster statistic')
        except ET.ParseError as error: raise ValueError('invalid auxiliary XML') from error
    return MEDIA[suffix]


def safe_name(name):
    p = PurePosixPath(name)
    if (not isinstance(name, str) or len(name) > 160 or '\\' in name or p.is_absolute()
            or any(part in ('', '.', '..') for part in name.split('/'))
            or not re.fullmatch(r'[A-Za-z0-9_./-]+', name)):
        raise ValueError('unsafe package path')
    return p


def write_bundle(source, target, metadata):
    source, target = Path(source), Path(target)
    if source.is_symlink() or not source.is_dir():
        raise ValueError('package source must be a regular directory')
    contents = {}
    for path in sorted(source.rglob('*')):
        if path.is_symlink(): raise ValueError('package symlinks are forbidden')
        if path.is_dir(): continue
        name = str(path.relative_to(source)); safe_name(name)
        if not path.is_file() or path.suffix not in MEDIA: raise ValueError('unsupported package member')
        if path.stat().st_size > MAX_BYTES: raise ValueError('oversize package member')
        contents[name] = path.read_bytes()
        checked_media(name, contents[name])
    if 'project.qgs' not in contents or len(contents) > MAX_FILES or sum(map(len, contents.values())) > MAX_BYTES:
        raise ValueError('invalid bounded project package')
    manifest = {'schema_version': 1, 'metadata': metadata,
                'assets': [{'path': name, 'length': len(data), 'sha256': digest(data),
                            'media_type': checked_media(name, data)} for name, data in contents.items()]}
    payload = dict(contents)
    payload['manifest.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    # Exclusive destination creation also prevents overwriting earlier publication evidence.
    with target.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in payload.items():
                info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, data)
    inspect_bundle(target)
    return manifest


def inspect_bundle(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES + 1024 * 1024:
        raise ValueError('invalid package file')
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = [row.filename for row in members]
            if len(members) > MAX_FILES + 1 or len(set(names)) != len(names):
                raise ValueError('too many or duplicate package entries')
            if sum(row.file_size for row in members) > MAX_BYTES + 65536:
                raise ValueError('uncompressed package exceeds limit')
            for row in members:
                safe_name(row.filename)
                mode = row.external_attr >> 16
                if (row.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                        or row.flag_bits & 1 or row.file_size > MAX_BYTES
                        or row.file_size > max(4096, row.compress_size * 100)):
                    raise ValueError('unsafe package member type or compression')
            if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size > 65536:
                raise ValueError('missing or excessive manifest')
            manifest = json.loads(archive.read('manifest.json'))
            if set(manifest) != {'schema_version', 'metadata', 'assets'} or manifest['schema_version'] != 1:
                raise ValueError('unknown package manifest')
            assets = manifest['assets']
            if not isinstance(assets, list) or len(assets) > MAX_FILES:
                raise ValueError('invalid asset list')
            declared = [row['path'] for row in assets]
            if len(set(declared)) != len(declared) or set(names) != set(declared) | {'manifest.json'} or 'project.qgs' not in declared:
                raise ValueError('package asset set differs')
            contents = {}
            for row in assets:
                name = row['path']; p = safe_name(name)
                if set(row) != {'path', 'length', 'sha256', 'media_type'} or MEDIA.get(p.suffix) != row['media_type']:
                    raise ValueError('unsupported package media type')
                data = archive.read(name)
                if checked_media(name,data) != row['media_type']: raise ValueError('package media differs')
                if type(row['length']) is not int or len(data) != row['length'] or digest(data) != row['sha256']:
                    raise ValueError('package asset content differs')
                contents[name] = data
            return manifest, contents
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError, RuntimeError) as error:
        raise ValueError('invalid package encoding') from error
