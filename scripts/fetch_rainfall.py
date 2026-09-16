"""Fetch SMHI daily archive and retain representative dates and UTC intervals."""
import csv, io, json, pathlib, datetime, urllib.request, sys, hashlib
root=pathlib.Path(__file__).resolve().parents[1]
url='https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/5/station/53530/period/corrected-archive/data.csv'
raw=pathlib.Path(sys.argv[1]).read_bytes() if len(sys.argv)>1 else urllib.request.urlopen(url,timeout=90).read()
lines=raw.decode('utf-8-sig').splitlines()
start=next(i for i,x in enumerate(lines) if x.startswith('Från Datum Tid'))
records=[]
for row in csv.reader(lines[start+1:],delimiter=';'):
    if len(row)>=5 and '2023-11-01'<=row[2]<='2023-11-21':
        records.append({'date':row[2],'fromUTC':row[0],'toUTC':row[1],'mm':float(row[3]) if row[3] else None,'quality':row[4]})
assert len(records)==21, 'Expected 21 daily records; inspect source before updating.'
payload={'station':{'id':53530,'name':'Hörby A','longitude':13.6673,'latitude':55.8624},'parameter':'Daily precipitation, 24-hour sum ending at 06:00 UTC','source':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archive_sha256':hashlib.sha256(raw).hexdigest(),'qualityCodes':{'G':'Checked and approved','Y':'Suspect or aggregated'},'note':'Dates are SMHI representative days, not midnight-to-midnight totals. Intervals are retained in the table. Station rainfall is not catchment-average rainfall and does not establish flood depth.','records':records}
(root/'web/data/rainfall.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
with (root/'web/data/rainfall.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=['date','fromUTC','toUTC','mm','quality']);writer.writeheader();writer.writerows(records)
print(json.dumps(records,ensure_ascii=False))
