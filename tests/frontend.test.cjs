const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
const durationContext = vm.createContext({});
vm.runInContext(script.slice(script.indexOf('function calculateDuration('),script.indexOf('function getPath(')),durationContext);
test('durations handle ongoing jobs, leap dates and missing precision',()=>{
    const cases=[['2026-02','Present','7 mos'],['2021-01','2023-09','2 yrs 8 mos'],
        ['2026-09-01','2026-09-10','9 days'],['2024-01-31','2024-02-29','29 days'],
        ['2024-02-30','2024-04-01',''],['2024','2025',''],['2025-06','2025-04','']];
    for(const [start,end,expected] of cases){
        assert.equal(vm.runInContext(`calculateDuration(${JSON.stringify(start)},${JSON.stringify(end)},new Date('2026-09-10T00:00:00Z'))`,durationContext),expected);
    }
});
test('editing dates updates calculated duration and exported data',()=>{
    const c=vm.createContext({});
    vm.runInContext(`const appState={extractedData:{experience:[{startDate:'2025-01',endDate:'2025-04',duration:''}],education:[]}};const input={value:'',parentElement:{dataset:{}}};const $=()=>input;const markDirty=()=>{};`,c);
    vm.runInContext(script.slice(script.indexOf('function calculateDuration('),script.indexOf('function markDirty(')),c);
    vm.runInContext("setPath(['experience',0,'endDate'],'2026-04')",c);
    assert.equal(vm.runInContext('input.value',c),'1 yr 3 mos');
    assert.equal(vm.runInContext('appState.extractedData.experience[0].duration',c),'1 yr 3 mos');
});
const context = vm.createContext({});
vm.runInContext('const appState={extractedData:null};\n'+script.slice(script.indexOf('function flattened('),script.indexOf('function exportData(')),context);
function evaluate(expression){return vm.runInContext(expression,context);}
test('JSON exports include edited nested fields and table cells',()=>{
    evaluate('appState.extractedData={personalInformation:{fullName:"Alex"},tables:[{headers:["H"],rows:[["before"]]}]}');
    evaluate('appState.extractedData.personalInformation.fullName="Əli Məmmədov";appState.extractedData.tables[0].rows[0][0]="after"');
    const result=JSON.parse(evaluate('exportContent("json")'));
    assert.equal(result.personalInformation.fullName,'Əli Məmmədov');
    assert.equal(result.tables[0].rows[0][0],'after');
});
test('CSV neutralizes formula prefixes and escapes quotes',()=>{
    assert.equal(evaluate('csvCell("=1+1")'),'"\'=1+1"');
    assert.equal(evaluate('csvCell("+994501234567")'),'"\'+994501234567"');
    assert.equal(evaluate('csvCell(\'a,"b"\')'),'"a,""b"""');
});
test('CSV retains unicode, newline text, arrays and empty collections',()=>{
    evaluate('appState.extractedData={summary:"təcrübə\\nsecond line",skills:["SQL"],tables:[]}');
    const result=evaluate('exportContent("csv")');
    assert.ok(result.startsWith('\ufeff"Field","Value"'));
    assert.ok(result.includes('təcrübə\nsecond line'));
    assert.ok(result.includes('"skills.0","SQL"'));
    assert.ok(result.includes('"tables","[]"'));
});
test('TXT exports all nested categories rather than just summary',()=>{
    evaluate('appState.extractedData={summary:"Hello",education:[{university:"Example"}],tables:[{rows:[["Cell"]]}]}');
    const result=evaluate('exportContent("txt")');
    assert.ok(result.includes('education.0.university: Example'));
    assert.ok(result.includes('tables.0.rows.0.0: Cell'));
});
