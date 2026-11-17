"""LOCAL SYNTHETIC rehearsal only. No remote Git, Actions or actual approvals.

Run from repository root with python -m tools.market_weather_rehearsal.
The source snapshot is read-only; output must be a new, isolated private folder.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys

from src.macro import weather_release as release, weather_publication as gate
from src.pipeline.layout import ROOT, configuration, copy_data, files, hashes
from src.pipeline.runner import compose


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    args=p.parse_args();source=args.snapshot.resolve();work=args.work.resolve()
    if work.exists() or work==ROOT or ROOT in work.parents or work==source or work in source.parents or source in work.parents:
        p.error('a fresh isolated work directory outside repository/snapshot is required')
    os.umask(0o077);work.mkdir(parents=True,mode=0o700)
    cfg=configuration();before=hashes(source,files(cfg));stage=work/'synthetic-stage';copy_data(source,stage,cfg)
    # Deliberately use the same SYNTHETIC fixture as Gate tests, never real r2.
    sys.path.insert(0,str(ROOT/'tests'))
    import test_weather_publication as fixture
    now=dt.datetime.now(dt.timezone.utc);fixture.NOW=now
    ctx,pub,trust,_,_=fixture.setup()
    authority=release.Authority(lambda:trust,lambda *_:[(ctx,pub)])
    request=release.PublicationRequest(authority,'market-weather-2026-09:1')
    request.apply(stage,ROOT,now)
    compose(ROOT,stage,work/'synthetic-pages',cfg,monthly_authority=authority,at=now)
    empty=work/'empty-stage';copy_data(source,empty,cfg)
    compose(ROOT,empty,work/'empty-pages',cfg,at=now)
    if before!=hashes(source,files(cfg)):raise RuntimeError('source_snapshot_changed')
    report={'fixture':'SYNTHETIC_ONLY','remote_operations':0,'actual_r2_public_json_count':0,
            'synthetic_release_verified':True,'empty_state_verified':True,'source_snapshot_unchanged':True,
            'synthetic_public_pair_sha256':hashes(stage,release.PUBLIC_FILES)}
    (work/'rehearsal-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return 0


if __name__=='__main__':raise SystemExit(main())
