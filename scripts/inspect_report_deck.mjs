import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/lisa2/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const root='D:/democase/ai';
const out=root+'/docs/10_完成快照_2026-10-10/排版核對';
const p=await PresentationFile.importPptx(await FileBlob.load(root+'/docs/08_簡報/AI_流程圖大全_給指導老師_2026-10-10.pptx'));
console.log(await p.inspect({kind:'slide,textbox,image,layout',maxChars:6000}));
for(const i of [0,1,22]) {
  const s=p.slides.items[i];
  console.log(i,s.shapes.items.map(x=>({id:x.id,text:String(x.text),position:x.position})),s.images.items.length);
  const b=await s.export({format:'png',scale:1});
  await fs.writeFile(out+'/deck-before-'+i+'.png',new Uint8Array(await b.arrayBuffer()));
}
