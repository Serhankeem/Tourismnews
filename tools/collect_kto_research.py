"""Actual public KTO XLSX acquisition into a NEW private research directory.

Reuses the production robots-aware transport, release/rights checks, workbook
parser and independent monthly/YTD checks. Never invokes engine.collect or writes
an operational ledger, public JSON, approval, workflow or web asset.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from src.macro import kto
from src.macro.transport import Loader, AccessError
from src.macro.model import months

ROOT = Path(__file__).resolve().parents[1]
IDS = frozenset({'kto_inbound', 'kto_outbound', 'kto_inbound_cn', 'kto_inbound_jp',
                 'kto_inbound_tw', 'kto_inbound_us', 'kto_inbound_vn'})


def external_new(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents or path in ROOT.parents or path.exists():
        raise ValueError('new_external_directory_required')
    return path


def capture(output, loader=None, now=None):
    output = external_new(output)
    config = json.loads((ROOT/'macro_sources.json').read_text())
    source = next(s for s in config['sources'] if s['id'] == 'kto_monthly_statistics')
    items = [i for i in config['indicators'] if i['source_id'] == source['id'] and i.get('enabled')]
    if not source.get('enabled') or {i['id'] for i in items} != IDS:
        raise ValueError('existing_kto_scope_changed')
    output.mkdir(parents=True, mode=0o700)
    real = loader is None
    loader = loader or Loader()
    now = now or dt.datetime.now(dt.timezone.utc)
    requests = []
    stage = 'public_release_discovery'

    def load(url):
        raw = loader(url)
        name = f'request-{len(requests)+1:02d}' + ('.xlsx' if raw.startswith(b'PK') else '.html')
        (output/name).write_bytes(raw)
        requests.append(dict(url=url, file=name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
        return raw

    try:
        period, url, catalog = kto.discover_release(source, load, now)
        stage = 'release_rights_and_file_controls'
        files, published = kto.release_files(load(url), url, period, now)
        stage = 'official_xlsx_download'
        primary, check = load(files['series']), load(files['crosscheck'])
        stage = 'normalization'
        values, locations = kto.parse_series(primary, period, items, source['start_period'])
        stage = 'monthly_continuity'
        expected = set(months(source['start_period'], period))
        if any(set(v) != expected for v in values.values()):
            raise ValueError('research_history_missing_months')
        stage = 'independent_month_prior_year_ytd_crosscheck'
        kto.crosscheck(check, period, values, items)
        snapshot = dict(reference_period=period, source_url=url, discovery_catalog_url=catalog,
                        release_published_at=published, collected_at=now.isoformat(),
                        values=values, locations=locations, unit='명', frequency='M', rights='KOGL-0',
                        file_url=files['series'], crosscheck_url=files['crosscheck'],
                        file_sha256=hashlib.sha256(primary).hexdigest(),
                        crosscheck_sha256=hashlib.sha256(check).hexdigest())
        (output/'snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2)+'\n')
        with (output/'normalized.csv').open('w', newline='') as f:
            writer = csv.writer(f, lineterminator='\n')
            writer.writerow(['indicator_id', 'period', 'value', 'unit', 'source_file_sha256'])
            for ident, observations in values.items():
                for p, v in sorted(observations.items()):
                    writer.writerow([ident, p, v, '명', snapshot['file_sha256']])
        result = dict(status='live_public_download_validated' if real else 'simulation_only',
                      actual_network_collection=real, stage='complete', reference_period=period,
                      series_months={k: len(v) for k, v in values.items()},
                      file_sha256=snapshot['file_sha256'], crosscheck_sha256=snapshot['crosscheck_sha256'],
                      no_production_writes=True)
    except Exception as exc:
        # Provider text, redirect bodies and unexpected exception strings never escape.
        fixed = {'robots_invalid', 'robots_disallowed', 'crawl_delay_requires_deferred_fetch',
                 'redirect_limit', 'response_too_large', 'unapproved_public_statistical_endpoint',
                 'unapproved_public_statistical_catalog', 'release_rights_changed_or_unverified',
                 'research_history_missing_months', 'independent_official_tables_disagree',
                 'prior_year_month_tables_disagree', 'year_to_date_tables_disagree',
                 'crosscheck_period_or_unit_unverified', 'required_official_files_missing'}
        message = str(exc) if isinstance(exc, (AccessError, ValueError)) else ''
        code = message if message in fixed or re.fullmatch(r'(?:robots_)?http_[1-5][0-9]{2}', message) else 'public_download_or_validation_failed'
        result = dict(status='failed', actual_network_collection=real, stage=stage,
                      error_code=code, no_production_writes=True)
    (output/'requests.json').write_text(json.dumps(requests, indent=2)+'\n')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = capture(args.output)
    except Exception:
        raise SystemExit('research_destination_or_configuration_invalid')
    print(json.dumps(result))
    if result['status'] != 'live_public_download_validated':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
