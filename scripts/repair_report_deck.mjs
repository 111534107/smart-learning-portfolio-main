import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {FileBlob,PresentationFile} from 'file:///C:/Users/lisa2/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const root='D:/democase/ai', skill='C:/Users/lisa2/.codex/plugins/cache/openai-primary-runtime/presentations/26.1007.11041/skills/presentations';
const work=root+'/docs/10_完成快照_2026-10-10/排版核對';
const p=await PresentationFile.importPptx(await FileBlob.load(root+'/docs/08_簡報/AI_流程圖大全_給指導老師_2026-10-10.pptx'));
const ds=JSON.parse(await fs.readFile(root+'/scripts/report-diagrams.json','utf8'));
for(let i=1;i<p.slides.items.length;i++){
 const slide=p.slides.items[i], [file,title]=ds[i-1];
 for(const sh of slide.shapes.items){
  const text=String(sh.text);
  if(/^圖\s*\d/.test(text))sh.text=title;
  else if(/原圖：|圖稿原始碼：|此頁保留|目前環境尚未/.test(text))sh.text='';
 }
 const bytes=await fs.readFile(root+'/docs/images/'+file);
 if(slide.images.items.length){
  const im=slide.images.items[0];im.replace({blob:bytes,contentType:'image/png',alt:title,fit:'contain'});
  im.frame={left:52.8,top:120,width:1176,height:542.4}; im.fit='contain';
 }else slide.images.add({blob:bytes,contentType:'image/png',alt:title,fit:'contain',position:{left:52.8,top:120,width:1176,height:542.4}});
}
await fs.mkdir(work+'/slides',{recursive:true});
await (await PresentationFile.exportPptx(p)).save(work+'/diagram-deck-candidate.pptx');
for(let i=0;i<p.slides.items.length;i++){
 const png=await p.slides.items[i].export({format:'png',scale:1});
 await fs.writeFile(work+'/slides/'+String(i+1).padStart(2,'0')+'.png',new Uint8Array(await png.arrayBuffer()));
 if(i%10===0)console.log('rendered',i+1);
}
const {finalizePresentation}=await import(pathToFileURL(skill+'/container_tools/artifact_tool_utils.mjs').href);
const result=await finalizePresentation({workspaceDir:root,candidatePath:work+'/diagram-deck-candidate.pptx',finalPath:root+'/docs/08_簡報/AI_流程圖大全_給指導老師_2026-10-10_圖名修訂版.pptx',pythonExecutable:'C:/Users/lisa2/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',layoutArgs:['--expected-slide-size-emu','12191695,6858000'],explicitTotalSlideCount:44,verifyArtifactToolImport:true,receiptPath:work+'/diagram-deck-validation.json'});
console.log(JSON.stringify(result));
