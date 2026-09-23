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

test('quick CV view exposes an eye toggle and compact panel',()=>{
    assert.ok(html.includes('id="quickPreviewBtn"'));
    assert.ok(html.includes('fa-regular fa-eye'));
    assert.ok(html.includes('id="quickPreviewPanel"'));
    assert.ok(html.includes('Quick CV view'));
});
const quickContext=vm.createContext({});
const quickStart=script.indexOf('function monthIndex(');
const quickEnd=script.indexOf('const EXPERIENCE_RANGES=',quickStart);
vm.runInContext(script.slice(quickStart,quickEnd),quickContext);
test('total experience merges overlapping work periods instead of double counting',()=>{
    const result=vm.runInContext(`formatExperienceMonths(totalExperienceMonths([{startDate:'2020-01',endDate:'2022-01'},{startDate:'2021-06',endDate:'2023-01'}],new Date('2026-09-23T00:00:00Z')))`,quickContext);
    assert.equal(result,'3 yrs');
});
test('current job is selected only from an explicitly ongoing experience entry',()=>{
    const current=vm.runInContext(`getCurrentExperience([{company:'Old',position:'Developer',endDate:'2024-12'},{company:'Active',position:'Lead',endDate:'Present'}])`,quickContext);
    assert.equal(current.company,'Active');
    assert.equal(current.position,'Lead');
    const none=vm.runInContext(`getCurrentExperience([{company:'Old',endDate:'2024-12'}])`,quickContext);
    assert.equal(none,null);
});

test('minimal redesign keeps results hidden until a CV is parsed',()=>{
    assert.ok(html.includes('id="resultsWorkspace" class="workspace-results" hidden'));
    assert.ok(html.includes('Upload a CV. Get the useful parts.'));
});
test('quick view is a modal containing the original PDF preview',()=>{
    assert.ok(html.includes('id="quickPreviewPanel" class="modal-backdrop"'));
    assert.ok(html.includes('id="quickPreviewContent"'));
    assert.ok(html.includes('Original CV'));
    assert.ok(html.includes('id="previewArea"'));
});
const rangeContext=vm.createContext({});
const rangeStart=script.indexOf("const EXPERIENCE_RANGES=");
const rangeEnd=script.indexOf("function experienceRangeField(",rangeStart);
vm.runInContext(script.slice(rangeStart,rangeEnd),rangeContext);
test('experience is grouped into editable review ranges',()=>{
    assert.equal(vm.runInContext('experienceRangeFromMonths(30)',rangeContext),'2–3 years');
    assert.equal(vm.runInContext('experienceRangeFromMonths(47)',rangeContext),'3–5 years');
    assert.equal(vm.runInContext('experienceRangeFromMonths(130)',rangeContext),'10+ years');
});

test('quick view contains only personal, contact and professional overview sections',()=>{
    const start=script.indexOf('function renderQuickPreview(){');
    const end=script.indexOf('function recalculateDurations()',start);
    const render=script.slice(start,end);
    for(const heading of ['Personal information','Contact & links','Professional overview']) assert.ok(render.includes(heading),heading);
    for(const removed of ['Middle name','Marital status','Professional summary','Current position','Work history','Education','Skills','Languages','Certifications','Projects']) assert.equal(render.includes(removed),false,removed);
});
test('quick view keeps essential fields editable and gender uses a dropdown',()=>{
    assert.ok(script.includes('function quickSetPath(path,value)'));
    assert.ok(script.includes('function quickGenderField()'));
    assert.ok(script.includes("['','Not specified']"));
    assert.ok(script.includes("['Male','Male']"));
    assert.ok(script.includes("['Female','Female']"));
    assert.ok(script.includes("['Other','Other']"));
    assert.ok(script.includes("quickEditField('Full name'"));
    assert.ok(script.includes("quickEditField('Email'"));
    assert.ok(script.includes('experienceRangeField(months)'));
});
test('quick modal is constrained to one viewport without an internal info scroll',()=>{
    assert.ok(html.includes('.quick-modal{height:min(760px,calc(100vh - 56px));min-height:0}'));
    assert.ok(html.includes('.quick-info-pane{overflow:hidden}'));
    assert.ok(html.includes('.quick-modal-body{min-height:0;overflow:hidden}'));
});
