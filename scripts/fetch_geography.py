"""Refresh current OSM reference geometry; never interpret it as a 2023 flood extent."""
import json, pathlib, urllib.request, urllib.parse, datetime
root = pathlib.Path(__file__).resolve().parents[1]
query = '''[out:json][timeout:45];(way["highway"](55.84,13.64,55.865,13.685);way["waterway"](55.84,13.64,55.865,13.685););out geom;'''
url='https://overpass-api.de/api/interpreter?'+urllib.parse.urlencode({'data':query})
req=urllib.request.Request(url,headers={'User-Agent':'HNA-research-demo/0.1'})
with urllib.request.urlopen(req,timeout=75) as response: raw=json.load(response)
features=[]
for e in raw['elements']:
    coords=[[p['lon'],p['lat']] for p in e.get('geometry',[]) if 'lon' in p]
    if len(coords)<2: continue
    tags=e.get('tags',{})
    features.append({'type':'Feature','id':str(e['id']),'properties':{'osm_id':e['id'],**tags},'geometry':{'type':'LineString','coordinates':coords}})
out={'type':'FeatureCollection','metadata':{'source':'OpenStreetMap contributors','license':'ODbL 1.0','source_url':'https://www.openstreetmap.org/copyright','retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'query':query,'warning':'Current reference geometry, not the road network at the event date; not an observed flood footprint.'},'features':features}
target=root/'web/data/geography.geojson'
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8')
print('Saved',len(features),'features')
for f in features:
    if f['properties'].get('name') in ['Ågatan','Tvärgatan','Hörbyån']:
        print(f['properties'].get('name'),f['id'],f['geometry']['coordinates'][len(f['geometry']['coordinates'])//2])
