const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let viewer,event,geo,rain,selected,topDown=false;
const groups={roads:[],river:[],impacts:[],station:[]};
const load=async path=>{const r=await fetch(path);if(!r.ok)throw new Error(`${path}: ${r.status}`);return r.json()};
function errorMap(message){$('map-error').hidden=false;$('map-error').textContent=message;}
function fly(lon=13.6547,lat=55.8491,range=1900){if(!viewer)return;const C=Cesium;viewer.camera.flyToBoundingSphere(new C.BoundingSphere(C.Cartesian3.fromDegrees(lon,lat,80),10),{duration:1.2,offset:new C.HeadingPitchRange(0,C.Math.toRadians(topDown?-90:-48),range)});}
function streetCoords(loc){const f=geo.features.find(f=>f.id===loc.representativeWay);return f.geometry.coordinates[Math.floor(f.geometry.coordinates.length/2)];}
function selectLocation(id,move=true){selected=event.locations.find(l=>l.id===id);if(!selected)return;
 $('selected-name').textContent=selected.name;$('selected-status').textContent=selected.status;$('selected-evidence').textContent=selected.evidence;$('next-step').textContent=selected.nextStep;
 document.querySelectorAll('.location').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===id)));
 if(move)fly(...streetCoords(selected),1050);
 if(viewer){for(const ent of groups.impacts){ent.point.pixelSize=ent.locationId===id?17:12;}viewer.scene.requestRender();}
}
function renderEvidence(){
 $('locations').innerHTML=event.locations.map((l,i)=>`<button class="location" data-id="${esc(l.id)}" aria-pressed="false"><strong>${i+1}. ${esc(l.name)}</strong><small>Impact reported · 17 November</small></button>`).join('');
 document.querySelectorAll('.location').forEach(b=>b.onclick=()=>selectLocation(b.dataset.id));
 $('spatial-caveat').textContent=event.spatialCaveat;$('source-link').href=event.source;$('gaps').innerHTML=event.gaps.map(g=>`<li>${esc(g)}</li>`).join('');
 $('dates').innerHTML=event.timeline.map((t,i)=>`<button data-index="${i}" aria-pressed="${i===0}">${esc(t.date.slice(8))} NOV<small>${esc(t.label)}</small></button>`).join('');
 $('timeline-text').textContent=event.timeline[0].text;
 $('dates').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('dates').querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));$('timeline-text').textContent=event.timeline[+b.dataset.index].text;});
 selectLocation(event.locations[0].id,false);
 $('brief').onclick=()=>{renderBrief();window.print();};
}
function renderRain(){
 const vals=rain.records.filter(r=>r.mm!==null), max=Math.max(...vals.map(r=>r.mm)), peak=vals.find(r=>r.mm===max);
 $('rain-summary').textContent=`${max.toFixed(1)} mm · highest daily total in view`;
 const W=680,H=140,pad=34,base=112,scale=82/Math.max(max,1),step=(W-pad-10)/rain.records.length;
 let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Daily precipitation from 1 to 21 November 2023 at Hörby A. Maximum ${max} millimetres on representative day ${peak.date}."><line x1="${pad}" x2="${W-10}" y1="${base}" y2="${base}" stroke="#cbdce3"/><text x="0" y="30" fill="#536f7d" font-size="12">${Math.ceil(max)} mm</text><text x="15" y="115" fill="#536f7d" font-size="12">0</text>`;
 rain.records.forEach((r,i)=>{const h=(r.mm??0)*scale,x=pad+i*step,color=r.date==='2023-11-17'?'#d95141':'#168c96';svg+=`<rect x="${x+3}" y="${base-h}" width="${step-6}" height="${h}" rx="2" fill="${color}"><title>${r.date}: ${r.mm??'Missing'} mm; quality ${r.quality}; ${r.fromUTC}–${r.toUTC} UTC</title></rect>`;if(i%3===0||r.date==='2023-11-17')svg+=`<text x="${x+step/2}" y="132" text-anchor="middle" font-size="11" fill="#536f7d">${r.date.slice(8)}</text>`;});
 $('rain-chart').innerHTML=svg+'</svg>';
 $('rain-note').innerHTML=`1–21 November 2023 · Representative days; 24-hour intervals ending at 06:00 UTC. Coral marks the 17 November report date, not a measured flood peak. <a href="${esc(rain.source)}" target="_blank" rel="noopener">SMHI archive</a> · <a href="data/rainfall.csv" download>Download CSV</a>`;
 $('rain-table').innerHTML='<table><thead><tr><th>Representative day</th><th>UTC interval</th><th>mm</th><th>Quality</th></tr></thead><tbody>'+rain.records.map(r=>`<tr><td>${r.date}</td><td>${r.fromUTC}<br>${r.toUTC}</td><td>${r.mm??'Missing'}</td><td>${esc(r.quality)}</td></tr>`).join('')+'</tbody></table><p class="fine">G: checked and approved. Y: suspect or aggregated. '+esc(rain.note)+'</p>';
}
function renderBrief(){ $('print-brief').innerHTML=`<h1>HNA · Hörby historical flood brief</h1><p>Event: 17–19 November 2023. Evidence checked ${esc(event.checked)}.</p><p>${esc(event.summary)}</p><section><h2>Documented street-level impacts</h2>${event.locations.map(l=>`<h3>${esc(l.name)}</h3><p>${esc(l.evidence)}</p><p><strong>Suggested investigation:</strong> ${esc(l.nextStep)}</p>`).join('')}</section><section><h2>Event updates</h2>${event.timeline.map(t=>`<p><strong>${esc(t.date)}:</strong> ${esc(t.text)}</p>`).join('')}</section><section><h2>Interpretation limits</h2><p>${esc(event.spatialCaveat)} ${esc(event.analysisStatus)}</p><ul>${event.gaps.map(g=>`<li>${esc(g)}</li>`).join('')}</ul></section><h2>Sources</h2><p>${esc(event.source)}</p><p>${rain?esc(rain.source):'Rainfall unavailable'}</p><p>OpenStreetMap contributors · ODbL · https://www.openstreetmap.org/copyright</p><p>HNA investigation prompts are suggestions, not municipal decisions.</p>`;}
function updateLayers(){if(!viewer)return;const alpha=+$('opacity').value/100;$('opacity-value').textContent=`${$('opacity').value}%`;for(const [group,entities] of Object.entries(groups)){entities.forEach(e=>{e.show=$(group).checked;if(e.polyline)e.polyline.material=Cesium.Color.fromCssColorString(group==='river'?'#168ecc':'#819ba8').withAlpha(alpha);});}viewer.scene.requestRender();}
async function initMap(){
 if(!window.Cesium){errorMap('The map library did not load. Check that the complete dist folder was deployed. The event evidence remains available.');return;}
 const C=Cesium;
 try{viewer=new C.Viewer('map',{baseLayer:false,baseLayerPicker:false,geocoder:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,animation:false,timeline:false,fullscreenButton:false,infoBox:false,selectionIndicator:false,requestRenderMode:true,msaaSamples:1,contextOptions:{webgl:{alpha:false,preserveDrawingBuffer:true}},terrainProvider:new C.EllipsoidTerrainProvider()});viewer.scene.highDynamicRange=false;}catch(e){errorMap('3D graphics are unavailable in this browser. Enable hardware acceleration or try a browser with WebGL2. The evidence panels remain usable.');console.error(e);return;}
 viewer.scene.globe.baseColor=C.Color.fromCssColorString('#d5e4e8');viewer.scene.backgroundColor=C.Color.fromCssColorString('#c4e4ee');viewer.scene.globe.enableLighting=false;
 viewer.scene.frameState.creditDisplay.addStaticCredit(new C.Credit('Reference data © <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a> · ODbL',true));
 let onlineLayer;
 const online=document.createElement('label');online.className='check';online.innerHTML='<input type="checkbox" id="online-basemap">OSM tile basemap · online';$('station').closest('label').after(online);
 $('online-basemap').onchange=()=>{if($('online-basemap').checked&&!onlineLayer){const imagery=new C.OpenStreetMapImageryProvider({url:'https://tile.openstreetmap.org/',credit:'© OpenStreetMap contributors'});onlineLayer=viewer.imageryLayers.addImageryProvider(imagery);imagery.errorEvent.addEventListener(()=>errorMap('Online basemap tiles are unavailable. Turn off the online basemap to use the bundled OpenStreetMap reference geometry.'));}if(onlineLayer)onlineLayer.show=$('online-basemap').checked;viewer.scene.requestRender();};
 const ids=new Map(event.locations.flatMap(l=>l.geometryIds.map(id=>[id,l.id])));
 for(const f of geo.features){const isRiver=!!f.properties.waterway;const group=isRiver?'river':'roads';const ent=viewer.entities.add({id:`osm-${f.id}`,name:f.properties.name||f.properties.highway||'Watercourse',polyline:{positions:C.Cartesian3.fromDegreesArray(f.geometry.coordinates.flat()),width:isRiver?3:1.5,clampToGround:true,material:C.Color.fromCssColorString(isRiver?'#168ecc':'#819ba8').withAlpha(.65)}});ent.locationId=ids.get(f.id);groups[group].push(ent);}
 event.locations.forEach((l,i)=>{const ent=viewer.entities.add({id:l.id,position:C.Cartesian3.fromDegrees(...streetCoords(l)),point:{pixelSize:12,color:C.Color.fromCssColorString('#d95141'),outlineColor:C.Color.WHITE,outlineWidth:3,heightReference:C.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:Number.POSITIVE_INFINITY},label:{text:`${i+1}  ${l.name}`,font:'bold 15px sans-serif',fillColor:C.Color.fromCssColorString('#133849'),showBackground:true,backgroundColor:C.Color.WHITE.withAlpha(.94),pixelOffset:new C.Cartesian2(0,-30),heightReference:C.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:Number.POSITIVE_INFINITY}});ent.locationId=l.id;groups.impacts.push(ent);});
 if(rain){const s=rain.station;groups.station.push(viewer.entities.add({id:'rain-station',position:C.Cartesian3.fromDegrees(s.longitude,s.latitude),point:{pixelSize:11,color:C.Color.fromCssColorString('#087e83'),outlineColor:C.Color.WHITE,outlineWidth:2,heightReference:C.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:Number.POSITIVE_INFINITY},label:{text:'SMHI · Hörby A',font:'14px sans-serif',showBackground:true,pixelOffset:new C.Cartesian2(0,-25),heightReference:C.HeightReference.CLAMP_TO_GROUND,disableDepthTestDistance:Number.POSITIVE_INFINITY}}));}
 viewer.screenSpaceEventHandler.setInputAction(m=>{const p=viewer.scene.pick(m.position);if(p?.id?.locationId)selectLocation(p.id.locationId,false);if(p?.id?.id==='rain-station')$('rain-chart').scrollIntoView({behavior:'smooth',block:'center'});},C.ScreenSpaceEventType.LEFT_CLICK);
 ['roads','river','impacts','station','opacity'].forEach(id=>$(id).oninput=updateLayers);
 $('reset').onclick=()=>fly();$('zoom-in').onclick=()=>{viewer.camera.zoomIn(viewer.camera.positionCartographic.height*.35);viewer.scene.requestRender();};$('zoom-out').onclick=()=>{viewer.camera.zoomOut(viewer.camera.positionCartographic.height*.45);viewer.scene.requestRender();};
 function mode(top){topDown=top;$('view2d').setAttribute('aria-pressed',String(top));$('view3d').setAttribute('aria-pressed',String(!top));fly();}
 $('view2d').onclick=()=>mode(true);$('view3d').onclick=()=>mode(false);fly();selectLocation(selected.id,false);
 $('terrain-status').textContent='Bundled OSM reference view · terrain loading';
 C.ArcGISTiledElevationTerrainProvider.fromUrl('https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer').then(provider=>{viewer.terrainProvider=provider;$('terrain-status').textContent='3D terrain · Esri World Elevation · context only';provider.errorEvent.addEventListener(()=>{$('terrain-status').textContent='Terrain service interrupted · detail may be incomplete';});viewer.scene.requestRender();}).catch(()=>{$('terrain-status').textContent='Flat-earth surface · elevation service unavailable';});
 window.hna={viewer,event,geo,rain,groups,selectLocation};
}
async function main(){try{[event,geo]=await Promise.all([load('data/event.json'),load('data/geography.geojson')]);renderEvidence();try{rain=await load('data/rainfall.json');renderRain();}catch(e){$('rain-note').textContent='Rainfall data unavailable. Check the deployed data folder.';console.error(e);}await initMap();$('data-status').textContent=`Sources checked ${event.checked}. ${geo.features.length} reference features loaded.`;}catch(e){errorMap('Case data could not load. Serve the complete dist directory over HTTP; opening index.html directly as a file is not supported.');$('data-status').textContent=e.message;console.error(e);}}
main();
