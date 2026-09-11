const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
const result = {match_percentage: 82.35, verdict: 'Highly Suitable', breakdown: {skill_match_score:80,semantic_similarity_score:85,experience_score:90,education_score:70}, skills_analysis:{matched_skills:['Python'],missing_skills:['Redis']},recommendations:['Review Redis experience.'],warnings:[]};
function setup(fetch) {
  const elements = new Map();
  const make = (tag='', cls='', text='') => ({tag,className:cls,textContent:text,hidden:true,disabled:false,value:'',children:[],attributes:{},style:{setProperty(k,v){this[k]=v;}},setAttribute(k,v){this.attributes[k]=v;},append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},addEventListener(){}});
  const $ = id => {if(!elements.has(id))elements.set(id,make());return elements.get(id);};
  $('jobRequirements').value='Python and Redis';
  const state={extractedData:{skills:{technical:['Python']}}};
  const context=vm.createContext({$,appState:state,node:make,apiBase:()=> 'https://parser.example',headers:()=>({'X-API-Key':'test-key'}),fetch,AbortController,setTimeout,clearTimeout,document:{querySelectorAll:()=>[]}});
  vm.runInContext(script.slice(script.indexOf('const jobMatchState='),script.indexOf('function calculateDuration(')),context);
  vm.runInContext(script.match(/function toggleActions\(enabled\).*\n/)[0],context);
  return {$,state,run:expression=>vm.runInContext(expression,context)};
}
test('panel opens for extracted CV and posts current edits with configured URL and key',async()=>{
  let request;
  const c=setup(async(url,options)=>{request={url,options};return {ok:true,json:async()=>result};});
  c.run('toggleActions(true)');
  assert.equal(c.$('jobPanel').hidden,false);
  c.state.extractedData.skills.technical.push('Docker');
  await c.run('analyzeJobCompatibility()');
  assert.equal(request.url,'https://parser.example/api/v1/match-job');
  assert.equal(request.options.headers['X-API-Key'],'test-key');
  assert.deepEqual(JSON.parse(request.options.body).cv_data.skills.technical,['Python','Docker']);
  assert.equal(c.$('jobMatchPercent').textContent,'82.3%');
  assert.equal(c.$('jobMatchResult').hidden,false);
  assert.equal(c.$('matchJobBtn').disabled,false);
});
test('changing CV or requirements discards an in-flight response',async()=>{
  let resolve;
  const c=setup(()=>new Promise(r=>{resolve=r;}));
  const pending=c.run('analyzeJobCompatibility()');
  c.run("invalidateJobMatch('CV edited')");
  resolve({ok:true,json:async()=>result});
  await pending;
  assert.equal(c.$('jobMatchResult').hidden,true);
  assert.equal(c.$('jobMatchStatus').textContent,'CV edited');
});
test('API validation errors allow retry and do not display a score',async()=>{
  const c=setup(async()=>({ok:false,status:422,json:async()=>({detail:[{msg:'CV data is incomplete'}]})}));
  await c.run('analyzeJobCompatibility()');
  assert.equal(c.$('jobMatchError').textContent,'CV data is incomplete');
  assert.equal(c.$('jobMatchResult').hidden,true);
  assert.equal(c.$('matchJobBtn').disabled,false);
});
test('empty requirements prevent requests and reset hides panel and score',async()=>{
  let calls=0;
  const c=setup(async()=>{calls++;return {ok:true,json:async()=>result};});
  c.$('jobRequirements').value='   ';
  await c.run('analyzeJobCompatibility()');
  assert.equal(calls,0);
  c.run('toggleActions(false)');
  assert.equal(c.$('jobPanel').hidden,true);
  assert.equal(c.$('jobMatchResult').hidden,true);
  assert.equal(c.$('jobRequirements').value,'');
});
test('untrusted score values are rejected and skill text is rendered as text',async()=>{
  const c=setup(async()=>({ok:true,json:async()=>({...result,match_percentage:101})}));
  await c.run('analyzeJobCompatibility()');
  assert.equal(c.$('jobMatchResult').hidden,true);
  assert.match(c.$('jobMatchError').textContent,/invalid match score/);
  const safe=setup(async()=>({ok:true,json:async()=>({...result,skills_analysis:{matched_skills:['<img src=x onerror=alert(1)>'],missing_skills:[]}})}));
  await safe.run('analyzeJobCompatibility()');
  const list=safe.$('jobMatchDetails').children.find(item=>item.tag==='ul');
  assert.equal(list.children[0].tag,'li');
  assert.equal(list.children[0].textContent,'<img src=x onerror=alert(1)>');
});

test('nested match scores appear inside their parent card', async()=>{
  const c=setup(async()=>({ok:true,json:async()=>({...result,breakdown:{...result.breakdown,skills:{hard_skills_match:75,tools_and_frameworks_match:50,soft_skills_match:100}}})}));
  await c.run('analyzeJobCompatibility()');
  const card=c.$('jobMatchBreakdown').children[0];
  assert.ok(card.children.some(child=>child.textContent==='hard skills match: 75.0%'));
  assert.ok(card.children.some(child=>child.textContent==='tools and frameworks match: 50.0%'));
});
