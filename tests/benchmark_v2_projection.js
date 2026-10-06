/* Run with node; no browser, saved account, Data Reader or evaluation execution. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/axiom_ui/assets/workbench-interactions.js', 'utf8');
const context = {window: {}};
vm.runInNewContext(source, context);
const ui = context.window.createAxiomInteractions({state: {benchmarkKey: 'SSE_COMPOSITE'},
  present: value => value !== null && value !== undefined,
  saved: value => value == null ? '未提供' : String(value)});
const view = {evaluation: {benchmark_comparisons: {SSE_COMPOSITE: {
  projection_version: 'benchmark_comparison_v2', status: 'COMPLETE', max_drawdown: '-0.25',
  series: [{account_session: '2026-01-02', native_session: '2026-01-02',
    normalized_index: '0.75', benchmark_drawdown: '-0.25'}]}}}};
const saved = ui.benchmark(view);
assert.equal(saved.max_drawdown, '-0.25');
assert.equal(saved.series[0].drawdown, '-0.25');
assert.equal(saved.series[0].nav_index, '0.75');
assert.equal(saved.series[0].session, '2026-01-02');
view.evaluation.benchmark_comparisons.SSE_COMPOSITE.projection_version = 'benchmark_comparison_v1';
assert.equal(ui.benchmark(view).series[0].drawdown, null);
assert.equal(ui.hasCandle([{open:'1.0',high:'1.2',low:'0.9',close:'1.1'}],
  {data_batch:null,native_chart:null}, true), true);
assert.equal(ui.hasCandle([{open:null,high:'1.2',low:'0.9',close:'1.1'}],
  {data_batch:null,native_chart:null}, true), false);
const displayPoint = {open:null,high:null,low:null,close:null,native_open:'1.0',
  native_high:'1.2',native_low:'0.9',native_close:'1.1'};
const originalPoint = {...displayPoint,open:displayPoint.native_open,high:displayPoint.native_high,
  low:displayPoint.native_low,close:displayPoint.native_close};
assert.equal(ui.hasCandle([displayPoint], {data_batch:null,native_chart:null}, true), false);
assert.equal(ui.hasCandle([originalPoint], {data_batch:null,native_chart:null}, true), true);
console.log('benchmark v2 owner point projection PASS');
