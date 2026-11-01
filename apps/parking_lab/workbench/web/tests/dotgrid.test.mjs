import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';

const libPath = path.join(process.cwd(), 'apps', 'parking_lab', 'workbench', 'web', 'lib', 'dotgrid.js');
await import('file:///' + libPath.split(path.sep).join('/'));

const { computeLayout } = globalThis.DotGrid;

test('a) count=0 -> all zeros', () => {
  const r = computeLayout({ count: 0, width: 800, maxHeight: 400 });
  assert.deepEqual(r, { cols: 0, rows: 0, size: 0, gap: 0, gridWidth: 0, gridHeight: 0, overflow: false });
});

test('b) count=1,width=800,maxHeight=400 -> 1x1 size 32', () => {
  const r = computeLayout({ count: 1, width: 800, maxHeight: 400 });
  assert.equal(r.cols, 1);
  assert.equal(r.rows, 1);
  assert.equal(r.size, 32);
  assert.equal(r.overflow, false);
});

test('c) count=7,width=600,maxHeight=300 -> 4x2 size 32', () => {
  const r = computeLayout({ count: 7, width: 600, maxHeight: 300 });
  assert.equal(r.cols, 4);
  assert.equal(r.rows, 2);
  assert.equal(r.size, 32);
  assert.equal(r.overflow, false);
});

test('d) count=60,width=900,maxHeight=420 default params', () => {
  const r = computeLayout({ count: 60, width: 900, maxHeight: 420 });
  assert.ok(Number.isInteger(r.cols) && r.cols >= 1);
  assert.equal(r.rows, Math.ceil(60 / r.cols));
  assert.ok(r.size <= 32);
  assert.ok(Math.abs(r.gap - r.size * 0.35) < 1e-9);
  assert.ok(r.gridWidth <= 900 + 1e-6);
  assert.ok(r.gridHeight <= 420 + 1e-6);
  assert.equal(r.overflow, false);
});

test('e) property loop count=1..200', () => {
  for (let count = 1; count <= 200; count++) {
    const r1 = computeLayout({ count, width: 900, maxHeight: 400 });
    const r2 = computeLayout({ count, width: 900, maxHeight: 400 });
    assert.deepEqual(r1, r2, 'deterministic for count=' + count);
    assert.ok(r1.cols >= 1 && Number.isInteger(r1.cols), 'cols valid count=' + count);
    assert.equal(r1.rows, Math.ceil(count / r1.cols), 'rows formula count=' + count);
    assert.ok(r1.gridWidth <= 900 + 1e-6 || r1.overflow === true, 'width bound count=' + count);
    assert.ok(r1.size <= 32, 'size cap count=' + count);
    for (const v of [r1.cols, r1.rows, r1.size, r1.gap, r1.gridWidth, r1.gridHeight]) {
      assert.ok(!Number.isNaN(v), 'no NaN count=' + count);
    }
  }
});

test('f) narrow container width=120,count=60,maxHeight=400', () => {
  const r = computeLayout({ count: 60, width: 120, maxHeight: 400 });
  assert.ok(r.cols >= 1);
  for (const v of [r.cols, r.rows, r.size, r.gap, r.gridWidth, r.gridHeight]) {
    assert.ok(Number.isFinite(v), 'finite output');
  }
});
