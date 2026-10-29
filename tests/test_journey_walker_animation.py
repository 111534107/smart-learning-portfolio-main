import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_returning_visit_walks_again_unless_reduced_motion():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required')
    script = Path(__file__).resolve().parents[1] / 'app/static/js/components.js'
    harness = r'''
const fs = require('fs');
const code = fs.readFileSync(process.argv[1], 'utf8');
const section = code.slice(code.indexOf('document.querySelectorAll("[data-walker]")'), code.indexOf('// ---------- 五年拼圖桌'));
function run(reduce) {
  let frames = 0, transform = '';
  const route = {getTotalLength: () => 800, getPointAtLength: n => ({x:100+n, y:140})};
  const svg = {getBoundingClientRect: () => ({width:1000}), querySelector: () => route, querySelectorAll: () => []};
  const walker = {ownerSVGElement:svg, dataset:{grade:'5'}, closest:()=>null,
    setAttribute: (_, value) => { transform=value; }, classList:{add(){}, remove(){}}};
  global.document = {documentElement:{dataset:{}}, querySelectorAll:()=>[walker], dispatchEvent(){}};
  global.window = {matchMedia:()=>({matches:reduce})};
  global.sessionStorage = {getItem:()=> '1', setItem(){}};
  global.CustomEvent = class {};
  global.performance = {now:()=>0};
  global.setTimeout = fn => fn();
  global.requestAnimationFrame = () => {frames++;};
  eval(section);
  return {frames, transform};
}
console.log(JSON.stringify({normal:run(false), reduced:run(true)}));
'''
    result = subprocess.run([node, '-e', harness, str(script)], check=True, capture_output=True, text=True, encoding='utf-8')
    states = json.loads(result.stdout)
    assert states['normal']['frames'] == 1
    assert states['reduced']['frames'] == 0
