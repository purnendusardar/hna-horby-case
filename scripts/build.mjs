import {cp, mkdir} from 'node:fs/promises';
await mkdir('dist/vendor/cesium', {recursive:true});
await cp('web', 'dist', {recursive:true});
// Scenario explorer docs (linked from web/scenarios/index.html as ../ASSUMPTIONS.md
// and ../scenarios.yaml) live at the repo root, not under web/, so they stay
// next to scenarios.yaml's sibling docs (README.md, VALIDATION.md). Copy them
// into dist explicitly rather than duplicating the files under web/.
await cp('scenarios.yaml', 'dist/scenarios.yaml');
await cp('ASSUMPTIONS.md', 'dist/ASSUMPTIONS.md');
const INTERNAL_DOCS = ['LAUNCH_CHECKLIST.md', 'OVERNIGHT_REPORT.md', 'RELEASE_REPORT.md', 'overnight_static.md', 'release_screenshots'];  // internal working docs/dirs are not published
await cp('docs', 'dist/docs', {recursive:true, filter: (src) => !INTERNAL_DOCS.some((n) => src.endsWith(n))});
await cp('node_modules/cesium/Build/Cesium', 'dist/vendor/cesium', {recursive:true});
await cp('node_modules/cesium/LICENSE.md', 'dist/vendor/cesium/LICENSE.md');
await cp('node_modules/cesium/ThirdParty.json', 'dist/vendor/cesium/ThirdParty.json');
await cp('node_modules/cesium/ThirdParty.extra.json', 'dist/vendor/cesium/ThirdParty.extra.json');
console.log('Built dist/ â€” deploy this directory to GitHub Pages.');
