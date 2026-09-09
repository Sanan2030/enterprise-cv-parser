const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
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
