import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

// charts.js 是浏览器 IIFE（末尾以 window 为全局）；这里在 Node 里注入空 window 加载纯函数。
const src = fs.readFileSync(path.join(process.cwd(), 'apps', 'parking_lab', 'workbench', 'web', 'lib', 'charts.js'), 'utf8');
const LabCharts = new Function('window', src + '\nreturn window.LabCharts;')({});
const { resolveHighlightRows, heatmapRowRect, highlightStyle } = LabCharts;

function visible(resolved) {
  return [resolved.hover, resolved.selected].filter(function (bay) { return bay !== null; });
}

test('悬停行优先于已选行：同时存在时只返回悬停行', () => {
  const r = resolveHighlightRows(104, 102, 90, 20);
  assert.deepEqual(r, { hover: 104, selected: null, priority: 'hover' });
  assert.equal(visible(r).length, 1);
});

test('无悬停时恢复已选行', () => {
  const r = resolveHighlightRows(null, 102, 90, 20);
  assert.deepEqual(r, { hover: null, selected: 102, priority: 'selected' });
  assert.equal(visible(r).length, 1);
});

test('连续扫过任意多行，解析结果始终最多一个可见行框', () => {
  for (let bay = 90; bay < 110; bay++) {
    const r = resolveHighlightRows(bay, 95, 90, 20);
    assert.ok(visible(r).length <= 1, 'bay ' + bay + ' 出现多个行框');
    assert.deepEqual(visible(r), [bay]);
  }
  const none = resolveHighlightRows(null, null, 90, 20);
  assert.equal(visible(none).length, 0);
});

test('分页外的车位（旧页码/越界）不画框，不产生幽灵高亮', () => {
  assert.equal(resolveHighlightRows(5, null, 90, 20).hover, null);
  assert.equal(resolveHighlightRows(120, 130, 90, 20).hover, null);
  assert.equal(resolveHighlightRows(95, 130, 90, 20).selected, null);
  assert.equal(resolveHighlightRows(null, 130, 90, 20).selected, null);
  assert.equal(resolveHighlightRows(null, 99, 90, 20).selected, 99);
});

test('非法行数/未初始化时不返回矩形', () => {
  const plot = { x: 40, y: 20, w: 500, h: 300 };
  assert.equal(heatmapRowRect(plot, 20, 0, 0, 3), null);
  assert.equal(heatmapRowRect(null, 20, 10, 0, 3), null);
  assert.equal(heatmapRowRect(plot, 0, 10, 0, 3), null);
});

test('行框只覆盖一行且落在绘图区内', () => {
  const plot = { x: 40, y: 20, w: 500, h: 300 };
  const box = heatmapRowRect(plot, 20, 10, 90, 94);
  assert.equal(box.x, 40.5);
  assert.equal(box.y, 20 + 4 * 20 + 0.5);
  assert.equal(box.width, 499);
  assert.equal(box.height, 19);
  assert.ok(box.y >= plot.y && box.y + box.height <= plot.y + plot.h);
});

test('高亮样式：只描边、无白色/半透明填充，悬停与选中可区分', () => {
  const hover = highlightStyle('hover');
  const selected = highlightStyle('selected');
  assert.equal(hover.fill, 'none');
  assert.equal(selected.fill, 'none');
  assert.ok(!('fill-opacity' in hover) && !('opacity' in hover));
  assert.ok(!('fill-opacity' in selected) && !('opacity' in selected));
  assert.equal(hover['pointer-events'], 'none');
  assert.equal(selected['pointer-events'], 'none');
  assert.notEqual(hover.stroke, selected.stroke);
  assert.ok(selected['stroke-dasharray']);
});
