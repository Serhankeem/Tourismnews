"""Read-only Publication Gate audit. No export path or approval issuance."""
import argparse
import datetime as dt
import json
from pathlib import Path
from src.macro import weather_publication as gate, weather_diagnostic as engine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editorial-record',type=Path,required=True)
    parser.add_argument('--trust-policy',type=Path,required=True)
    parser.add_argument('--publication-record',type=Path)
    args=parser.parse_args()
    try:
        now=dt.datetime.now(dt.timezone.utc);trust=gate.trust_file(args.trust_policy)
        ctx=gate.load_context(args.editorial_record,trust,now)
        publication=args.publication_record.read_bytes() if args.publication_record else None
        report=gate.audit(ctx,publication,trust,now,engine.read(engine.ROOT/'macro_sources.json'),engine.read(engine.ROOT/'operating_policy.json'))
        print(json.dumps(report));return 0 if report['publication_verified'] else 1
    except Exception:
        print(json.dumps({'reason':'approval_or_trust_invalid','public_json_generated':False}));return 1


if __name__=='__main__':raise SystemExit(main())
