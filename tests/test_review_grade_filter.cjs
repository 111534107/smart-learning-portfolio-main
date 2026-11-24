// 成績確認頁的課程篩選與成績鎖定（11-06 改版：三個切換按鈕＋「允許修改成績」勾選框）
// 執行：node --test tests/test_review_grade_filter.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'templates', 'learning_profile_review.html'), 'utf8',
);
const script = template.match(/<script id="review-course-script">([\s\S]*?)<\/script>/)?.[1];

function element(dataset = {}) {
  const listeners = {};
  const classes = new Set();
  return {
    dataset, hidden: false, value: '', textContent: '', checked: false, readOnly: false,
    children: [], listeners, attributes: {},
    classList: {
      toggle(name, on) { if (on) classes.add(name); else classes.delete(name); },
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    addEventListener(event, handler) { listeners[event] = handler; },
    setAttribute(key, value) { this.attributes[key] = value; },
    getAttribute(key) { return this.attributes[key] ?? null; },
    append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

function viewButton(view, pressed) {
  const button = element({ reviewView: view });
  button.attributes['aria-pressed'] = pressed ? 'true' : 'false';
  return button;
}

// 假的頁面：每列是 [年級, 種類, 需核對, 課名, 成績, 學分]
function page(rowSpecs, startView = 'review') {
  const grade = element(); grade.value = 'all';
  const views = ['review', 'failed', 'all', 'retake'].map((view) => viewButton(view, view === startView));
  const showAll = element();
  const rest = element();
  const allow = element();
  const allowLabel = element();
  const unlocked = element();
  const status = element();
  const changed = element();
  const empty = element();
  const scoreInputs = [];
  const courseInputs = [];
  const rows = rowSpecs.map(([gradeKey, kind, attention, name, score, credits, retake = false], index) => {
    const row = element({
      courseIndex: String(index), reviewGrade: gradeKey, reviewKind: kind,
      attention: attention ? 'true' : 'false', schoolYear: '114', reviewRetake: retake ? 'true' : 'false',
    });
    const inputs = {};
    for (const [field, value] of [['course_name', name], ['score', score], ['credits', credits], ['semester', '第一學期']]) {
      const input = element();
      input.name = `course_${index}_${field}`;
      input.value = value;
      input.defaultValue = value;
      inputs[field] = input;
      courseInputs.push(input);
    }
    scoreInputs.push(inputs.score);
    row.querySelector = (selector) => {
      for (const field of ['course_name', 'score', 'credits', 'semester']) {
        if (selector.includes(`_${field}"`)) return inputs[field];
      }
      return null;
    };
    row.inputs = inputs;
    return row;
  });
  const heading = element(); heading.dataset.heading = '及格課程';
  const section = element();
  section.querySelector = (selector) => (selector === 'h4' ? heading : null);
  section.querySelectorAll = () => rows.filter((row) => row.dataset.reviewGrade === '1');
  const groups = ['1', '2'].map((key) => {
    const group = element({ reviewGrade: key, reviewEmpty: 'false' });
    const groupRows = rows.filter((row) => row.dataset.reviewGrade === key);
    group.querySelectorAll = (selector) => (selector.startsWith('tr[') ? groupRows
      : (selector === '.course-review-section' && key === '1') ? [section] : []);
    return group;
  });
  const ids = new Map([
    ['review-grade-filter', grade], ['review-rest', rest], ['allow-score-edit', allow],
    ['allow-score-edit-label', allowLabel], ['scores-unlocked', unlocked],
    ['score-lock-status', status], ['review-changed-count', changed],
    ['review-filter-empty', empty],
  ]);
  const document = {
    getElementById(id) { return ids.get(id) || null; },
    querySelector(selector) { return selector === '[data-review-show-all]' ? showAll : null; },
    querySelectorAll(selector) {
      if (selector === '[data-review-view]') return views;
      if (selector.includes('.course-year-group')) return groups;
      if (selector.includes('input[name$="_score"]')) return scoreInputs;
      if (selector.includes('input[name^="course_"]')) return courseInputs;
      return [];
    },
    createElement() { return element(); },
  };
  vm.runInNewContext(script, { document, Array, Number, Boolean });
  return { grade, views, showAll, rest, allow, allowLabel, unlocked, status, changed, empty, rows, groups, heading };
}

test('the review script exists and the old three-state lock is gone', () => {
  assert.ok(script);
  assert.doesNotMatch(template, /id="lock-all-scores"|id="all-fields-locked"|review-makeup-filter|review-failure-filter/);
  assert.match(template, /id="allow-score-edit"/);
});

test('starts on courses that need checking; failed and all views switch the list', () => {
  const p = page([
    ['1', 'passed', true, '程式設計', '', ''],
    ['1', 'passed', false, '國文', '80', '2'],
    ['2', 'failed', true, '微積分', '52', '3'],
  ]);
  assert.deepEqual(p.rows.map((row) => row.hidden), [false, true, false]);
  assert.equal(p.rest.hidden, false);
  assert.equal(p.heading.textContent, '及格課程（1 門）');

  p.views[1].listeners.click();
  assert.deepEqual(p.rows.map((row) => row.hidden), [true, true, false]);
  assert.equal(p.views[1].attributes['aria-pressed'], 'true');
  assert.equal(p.views[0].attributes['aria-pressed'], 'false');
  assert.equal(p.rest.hidden, true);

  p.showAll.listeners.click();
  assert.deepEqual(p.rows.map((row) => row.hidden), [false, false, false]);
  assert.equal(p.views[2].attributes['aria-pressed'], 'true');
});

test('a missing credit counts as needing review even when not flagged', () => {
  const p = page([['1', 'passed', false, '國文', '80', ''], ['1', 'passed', false, '英文', '90', '2']]);
  assert.deepEqual(p.rows.map((row) => row.hidden), [false, true]);
});

test('retake filter shows both original and passing rows and combines with grade', () => {
  const p = page([
    ['1', 'resolved', false, '模擬程式', '58', '3', true],
    ['1', 'passed', false, '模擬程式', '85', '3', true],
    ['1', 'passed', false, '國文', '80', '2'],
    ['2', 'failed', true, '模擬統計', '55', '3', true],
  ], 'all');
  p.views.find(b => b.dataset.reviewView === 'retake').listeners.click();
  assert.deepEqual(p.rows.map(row => row.hidden), [false, false, true, false]);
  p.grade.value = '1'; p.grade.listeners.change();
  assert.deepEqual(p.rows.map(row => row.hidden), [false, false, true, true]);
  p.views.find(b => b.dataset.reviewView === 'failed').listeners.click();
  assert.deepEqual(p.rows.map(row => row.hidden), [true, true, true, true]);
  assert.equal(p.empty.hidden, false);
  assert.match(p.empty.textContent, /沒有尚未補過的課程/);
});

test('grade filter combines with the view and hides other grades', () => {
  const p = page([['1', 'failed', true, '國文', '40', '2'], ['2', 'failed', true, '微積分', '52', '3']], 'all');
  p.grade.value = '2';
  p.grade.listeners.change();
  assert.deepEqual(p.rows.map((row) => row.hidden), [true, false]);
  assert.deepEqual(p.groups.map((group) => group.hidden), [true, false]);
});

test('scores are locked by default; the checkbox is the only switch; clicking a locked score explains why', () => {
  const p = page([['1', 'passed', false, '國文', '80', '2']], 'all');
  const score = p.rows[0].inputs.score;
  assert.equal(score.readOnly, true);
  assert.equal(p.unlocked.value, '0');
  assert.equal(p.status.textContent, '成績已鎖定，避免誤改');

  score.listeners.click();
  assert.match(p.status.textContent, /先勾選上方的「允許修改成績」/);
  assert.ok(p.allowLabel.classList.contains('is-attention'));

  p.allow.checked = true;
  p.allow.listeners.change();
  assert.equal(score.readOnly, false);
  assert.equal(p.unlocked.value, '1');
  assert.ok(!p.allowLabel.classList.contains('is-attention'));

  p.allow.checked = false;
  p.allow.listeners.change();
  assert.equal(score.readOnly, true);
  assert.equal(p.unlocked.value, '0');
});

test('the save bar counts edited cells', () => {
  const p = page([['1', 'passed', false, '國文', '80', '2']], 'all');
  assert.equal(p.changed.textContent, '還沒有修改');
  const credits = p.rows[0].inputs.credits;
  credits.value = '3';
  credits.listeners.input();
  assert.equal(p.changed.textContent, '已修改 1 格');
});
