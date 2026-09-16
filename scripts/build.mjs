import {cp, mkdir} from 'node:fs/promises';
await mkdir('dist/vendor/cesium', {recursive:true});
await cp('web', 'dist', {recursive:true});
await cp('node_modules/cesium/Build/Cesium', 'dist/vendor/cesium', {recursive:true});
await cp('node_modules/cesium/LICENSE.md', 'dist/vendor/cesium/LICENSE.md');
await cp('node_modules/cesium/ThirdParty.json', 'dist/vendor/cesium/ThirdParty.json');
await cp('node_modules/cesium/ThirdParty.extra.json', 'dist/vendor/cesium/ThirdParty.extra.json');
console.log('Built dist/ — deploy this directory to GitHub Pages.');
