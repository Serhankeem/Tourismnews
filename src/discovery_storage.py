"""Lossless private discovery JSON envelope. Public files never use this codec."""
import base64
import gzip
import hashlib
import io
import json

FORMAT='tourism-discovery-gzip-v1'
MAX_UNCOMPRESSED=512*1024*1024


def encode(doc):
    raw=json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(raw)>MAX_UNCOMPRESSED:raise ValueError('discovery_logical_size_limit')
    return dict(storage_format=FORMAT,payload_sha256=hashlib.sha256(raw).hexdigest(),
                uncompressed_bytes=len(raw),payload_base64=base64.b64encode(gzip.compress(raw,compresslevel=6,mtime=0)).decode('ascii'))


def decode(doc):
    if not isinstance(doc,dict) or 'storage_format' not in doc:return doc
    if (set(doc)!={'storage_format','payload_sha256','uncompressed_bytes','payload_base64'} or doc['storage_format']!=FORMAT
            or type(doc['uncompressed_bytes']) is not int or not 0<=doc['uncompressed_bytes']<=MAX_UNCOMPRESSED):
        raise ValueError('discovery_storage_envelope_invalid')
    try:
        packed=base64.b64decode(doc['payload_base64'],validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:raw=stream.read(doc['uncompressed_bytes']+1)
        if len(raw)!=doc['uncompressed_bytes'] or hashlib.sha256(raw).hexdigest()!=doc['payload_sha256']:
            raise ValueError('discovery_storage_integrity_invalid')
        logical=json.loads(raw)
        if not isinstance(logical,dict) or 'storage_format' in logical:raise ValueError('discovery_storage_payload_invalid')
        return logical
    except (OSError,EOFError,TypeError,ValueError):raise ValueError('discovery_storage_integrity_invalid') from None
