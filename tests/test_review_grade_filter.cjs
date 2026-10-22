const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element(dataset = {}) {
  const listeners = {};
  return {
    dataset, hidden: false, value: '', textContent: '', checked: false,
    children: [], listeners, attributes: {}, classList: { toggle() {} },
    addEventListener(event, handler) { listeners[event] = handler; },
    setAttribute(key, value) { this.attributes[key] = value; },
    append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

test('per-table score lock icons are removed while the all-fields lock remains', () => {
  const template = fs.readFileSync(
    path.join(__dirname, '..', 'app', 'templates', 'learning_profile_review.html'), 'utf8',
  );
  assert.doesNotMatch(template, /score_lock_button|toggle-score-lock|score-unlock/);
  assert.match(template, /id="lock-all-scores"/);
  assert.match(template, /成績已鎖定，避免誤改/);
});

test('grade, failure and makeup filters intersect and update collapsed top-three summary', () => {
  const template = fs.readFileSync(
    path.join(__dirname, '..', 'app', 'templates', 'learning_profile_review.html'), 'utf8',
  );
  const script = template.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);
  const grade = element(); grade.value = 'all';
  const failure = element(); failure.value = 'all';
  const makeup = element(); makeup.value = 'all';
  const unlocked = element();
  const allLocked = element();
  const unlockButton = element();
  const lockStatus = element();
  const scoreInputs = [];

  function courseRow(index, gradeValue, kind, season, name, score, semester) {
    const row = element({
      courseIndex: String(index), reviewGrade: gradeValue, reviewKind: kind,
      makeupSeason: season, schoolYear: '114', needsReview: index === 0 ? 'true' : 'false',
    });
    const nameInput = element(); nameInput.value = name;
    const scoreInput = element(); scoreInput.value = String(score); scoreInput.readOnly = true;
    const semesterInput = element(); semesterInput.value = semester;
    scoreInputs.push(scoreInput);
    row.querySelector = (selector) => selector.includes('_course_name') ? nameInput
      : selector.includes('_score') ? scoreInput
        : selector.includes('_semester') ? semesterInput : null;
    return row;
  }
  const rowA = courseRow(0, '1', 'failed', 'summer', '暑期課', 55, '第一學期');
  const rowB = courseRow(1, '1', 'passed', 'winter', '寒期課', 75, '第二學期');
  const rowC = courseRow(2, '2', 'failed', 'summer', '二年級課', 40, '第一學期');
  const rows = [rowA, rowB, rowC];
  const sections = [];
  const empty = element(); empty.hidden = true;
  const summaries = new Map();
  const groups = ['1', '2'].map((gradeValue) => {
    const groupRows = rows.filter((row) => row.dataset.reviewGrade === gradeValue);
    const group = element({ reviewGrade: gradeValue, reviewEmpty: 'false' });
    const summary = element();
    summaries.set(gradeValue, summary);
    group.querySelectorAll = (selector) => selector.startsWith('tr[') ? groupRows
      : selector === '.course-review-section' ? sections : [];
    group.querySelector = (selector) => selector === '.course-year-group__empty' ? empty
      : selector === '.course-year-group__top-three' ? summary : null;
    return group;
  });
  const controls = new Map([
    ['review-grade-filter', grade], ['review-failure-filter', failure],
    ['review-makeup-filter', makeup], ['toggle-score-lock', unlockButton],
    ['scores-unlocked', unlocked], ['score-lock-status', lockStatus],
    ['all-fields-locked', allLocked],
  ]);
  const document = {
    getElementById(id) { return controls.get(id) || null; },
    querySelectorAll(selector) {
      if (selector.includes('.course-year-group')) return groups;
      if (selector.includes('input[name$="_score"]')) return scoreInputs;
      return [];
    },
    createElement() { return element(); },
  };
  vm.runInNewContext(script, { document, Array, Number });
  assert.deepEqual([rowA.hidden, rowB.hidden, rowC.hidden], [false, false, false]);

  grade.value = '1'; failure.value = 'failed'; makeup.value = 'summer';
  grade.listeners.change(); failure.listeners.change(); makeup.listeners.change();
  assert.deepEqual([rowA.hidden, rowB.hidden, rowC.hidden], [false, true, true]);
  assert.equal(summaries.get('1').children.length, 1);
  assert.match(summaries.get('1').children[0].textContent, /暑期課.*55 分.*第一學期.*114 學年度/);

  failure.value = 'pending';
  failure.listeners.change();
  assert.deepEqual([rowA.hidden, rowB.hidden, rowC.hidden], [true, true, true]);
  makeup.value = 'winter';
  makeup.listeners.change();
  assert.deepEqual([rowA.hidden, rowB.hidden, rowC.hidden], [true, true, true]);
});

test('pending filter shows only rows with missing credits', () => {
  const template = fs.readFileSync(
    path.join(__dirname, '..', 'app', 'templates', 'learning_profile_review.html'), 'utf8',
  );
  const script = template.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  const grade = element(); grade.value = 'all';
  const failure = element(); failure.value = 'all';
  const makeup = element(); makeup.value = 'all';
  const unlocked = element();
  const allLocked = element();
  const lockStatus = element();
  const pendingRow = element({courseIndex:'0',reviewGrade:'1',reviewKind:'passed',needsReview:'false',makeupSeason:''});
  const completeRow = element({courseIndex:'1',reviewGrade:'1',reviewKind:'pending',needsReview:'true',makeupSeason:''});
  const rows = [pendingRow, completeRow];
  for (const [row, name, score, semester] of [[pendingRow,'待確認課程','80','第一學期'],[completeRow,'一般課程','90','第二學期']]) {
    const nameInput = element(); nameInput.value = name;
    const scoreInput = element(); scoreInput.value = score;
    const creditsInput = element(); creditsInput.value = row === pendingRow ? '' : '2';
    const semesterInput = element(); semesterInput.value = semester;
    row.querySelector = (selector) => selector.includes('_course_name') ? nameInput
      : selector.includes('_score') ? scoreInput
        : selector.includes('_credits') ? creditsInput
        : selector.includes('_semester') ? semesterInput : null;
  }
  const heading = element();
  heading.dataset.heading = '及格課程';
  const section = element();
  section.querySelector = (selector) => selector === 'h4' ? heading : null;
  section.querySelectorAll = (selector) => selector.startsWith('tr[') ? rows : [];
  const group = element({reviewGrade:'1',reviewEmpty:'false'});
  group.querySelectorAll = (selector) => selector.startsWith('tr[') ? rows
    : selector === '.course-review-section' ? [section] : [];
  group.querySelector = () => null;
  const controls = new Map([
    ['review-grade-filter',grade], ['review-failure-filter',failure], ['review-makeup-filter',makeup],
    ['scores-unlocked',unlocked], ['all-fields-locked',allLocked], ['score-lock-status',lockStatus],
  ]);
  const document = {
    getElementById(id) { return controls.get(id) || null; },
    querySelectorAll(selector) {
      if (selector.includes('.course-year-group')) return [group];
      if (selector.includes('input[name$="_score"]')) return [];
      return [];
    },
    createElement() { return element(); },
  };
  vm.runInNewContext(script, {document,Array,Number});
  assert.equal(heading.textContent, '及格課程（2 門）');
  failure.value = 'pending';
  failure.listeners.change();
  assert.equal(heading.textContent, '及格課程（1 門）');
});

test('score remains readonly by default without a per-table lock control', () => {
  const template = fs.readFileSync(
    path.join(__dirname, '..', 'app', 'templates', 'learning_profile_review.html'), 'utf8',
  );
  const script = template.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);
  const grade = element(); grade.value = 'all';
  const failure = element(); failure.value = 'all';
  const makeup = element(); makeup.value = 'all';
  const unlocked = element();
  const allLocked = element();
  const lockStatus = element();
  const score = element(); score.value = '91'; score.readOnly = true;
  const group = element({ reviewGrade: '1', reviewEmpty: 'false' });
  group.querySelectorAll = () => [];
  group.querySelector = () => null;
  const controls = new Map([
    ['review-grade-filter', grade], ['review-failure-filter', failure],
    ['review-makeup-filter', makeup],
    ['scores-unlocked', unlocked], ['score-lock-status', lockStatus],
    ['all-fields-locked', allLocked],
  ]);
  const document = {
    getElementById(id) { return controls.get(id) || null; },
    querySelectorAll(selector) {
      if (selector.includes('.course-year-group')) return [group];
      if (selector.includes('input[name$="_score"]')) return [score];
      return [];
    },
    createElement() { return element(); },
  };
  vm.runInNewContext(script, { document, Array, Number });
  assert.equal(score.readOnly, true);
  assert.equal(unlocked.value, '0');
  assert.equal(lockStatus.textContent, '成績已鎖定，避免誤改');
  assert.match(template, /position: sticky/);
  assert.match(template, /成績已鎖定，避免誤改/);
  assert.match(template, /thead th \{ position: sticky; top: 0;/);
});

test('toolbar toggles every course field while default state keeps only scores locked', () => {
  const template = fs.readFileSync(path.join(__dirname, '..', 'app', 'templates', 'learning_profile_review.html'), 'utf8');
  const script = template.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  const grade = element(); grade.value = 'all';
  const failure = element(); failure.value = 'all';
  const makeup = element(); makeup.value = 'all';
  const master = element();
  const status = element();
  const scoresUnlocked = element();
  const allLocked = element();
  const fields = ['course_name', 'credits', 'score', 'semester', 'grade_level'].map((name) => {
    const input = element(); input.name = `course_0_${name}`; input.readOnly = name === 'score';
    return input;
  });
  const group = element({ reviewGrade: '1', reviewEmpty: 'false' });
  group.querySelectorAll = () => [];
  const controls = new Map([
    ['review-grade-filter', grade], ['review-failure-filter', failure], ['review-makeup-filter', makeup],
    ['lock-all-scores', master], ['score-lock-status', status], ['scores-unlocked', scoresUnlocked],
    ['all-fields-locked', allLocked],
  ]);
  const document = {
    getElementById(id) { return controls.get(id) || null; },
    querySelectorAll(selector) {
      if (selector.includes('.course-year-group')) return [group];
      if (selector.includes('.toggle-score-lock')) return [];
      if (selector.includes('input[name^="course_"]')) return fields;
      if (selector.includes('input[name$="_score"]')) return [fields[2]];
      return [];
    }, createElement() { return element(); },
  };
  vm.runInNewContext(script, { document, Array, Number });
  assert.equal(fields[0].readOnly, false);
  assert.equal(fields[2].readOnly, true);
  master.listeners.click();
  assert.ok(fields.every((input) => input.readOnly));
  assert.equal(allLocked.value, '1');
  master.listeners.click();
  assert.ok(fields.every((input) => !input.readOnly));
  assert.equal(allLocked.value, '0');
  assert.equal(scoresUnlocked.value, '1');
});
