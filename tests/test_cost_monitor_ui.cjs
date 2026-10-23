const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web/app.js','utf8');
function functionSource(name){const start=source.indexOf('function '+name+'(');const tail=source.slice(start);const next=tail.slice(1).search(/\n(?:async )?function /);return next<0?tail:tail.slice(0,next+1);}
test('fixed-cost custom range is independent of Overview dates',()=>{
 const ctx={Date,isoDate:d=>d.toISOString().slice(0,10),costState:{startDate:'2026-10-01',endDate:'2026-10-07'}};
 vm.createContext(ctx);vm.runInContext(functionSource('computeRangeDates'),ctx);
 const actual=ctx.computeRangeDates('custom',{startDate:'2026-10-15',endDate:'2026-10-20'});
 assert.equal(actual.start,'2026-10-15');assert.equal(actual.end,'2026-10-20');
 assert.equal(ctx.computeRangeDates('custom').start,'2026-10-01');
});
test('Overview summary excludes overhead and uses variable-spend average',()=>{
 function element(){return {children:[],append(...items){this.children.push(...items)},appendChild(item){this.children.push(item)}};}
 const panel=element();const ctx={costState:{provider:''},$:()=>panel,document:{createElement:element},fmtUsd:v=>String(v)};
 vm.createContext(ctx);vm.runInContext(functionSource('renderCostSummary'),ctx);
 ctx.renderCostSummary({variable_cost_usd:'6',total_cost_usd:'106',call_count:2,avg_cost_per_call_usd:'53',fixed_cost_usd:'100',total_billed_minutes:'3'});
 const rows=panel.children.map(row=>row.children.map(x=>x.textContent));
 assert.equal(rows.find(r=>r[0]==='Variable spend')[1],'6');
 assert.equal(rows.find(r=>r[0]==='Variable spend / call')[1],'3');
 assert.equal(rows.some(r=>r[0]==='Fixed'),false);
});
test('missing backend metrics show unavailable rather than fabricated zero',()=>{
 const ctx={};vm.createContext(ctx);vm.runInContext(functionSource('costReportingSummary'),ctx);
 assert.throws(()=>ctx.costReportingSummary({summary:{total_cost_usd:'1'}}),/backend update required/);
});
test('billed minutes sort numerically',()=>{
 const ctx={costState:{sortKey:'billed_minutes',sortDir:'asc'}};vm.createContext(ctx);vm.runInContext(functionSource('sortCalls'),ctx);
 assert.equal(ctx.sortCalls([{billed_minutes:'10'},{billed_minutes:'2'}])[0].billed_minutes,'2');
});
test('Cost tab initializes against actual HTML without missing elements',()=>{
 const html=fs.readFileSync('web/index.html','utf8');
 const elements=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],{classList:{toggle(){},add(){},remove(){}},addEventListener(){}}]));
 const ctx={$:id=>elements.get(id)||null,document:{querySelectorAll:()=>[]}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('// ── cost monitor')),ctx);
 assert.equal(typeof elements.get('cost-subtab-rates').onclick,'function');
 assert.equal(typeof elements.get('fixed-cost-custom-apply').onclick,'function');
});
