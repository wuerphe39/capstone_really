// Record actual Flutter file uploads, review, and Gemini RAG for each fixture.
// Uses an isolated DB/API started separately; no API seeding or synthetic UI data.
const fs=require('fs');
const path=require('path');
const {chromium}=require('playwright');
const visitor=process.argv.includes('--visitor');
const output=path.resolve(`artifacts/ai_sound_demo_20261012/${visitor?'visitor':'natural'}`);
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const cases=visitor ? [
 {name:'visitor_sequence',file:'doorbell_knock_then_bark.wav',label:null,
  source:'집에 초인종 소리가 나고 노크 소리가 들린 뒤 개가 짖는 소리가 들립니다.'},
] : [
 {name:'detected',file:'bark_tts_0.2.wav',label:'pet_vocalization',
  note:'공개 짖음 원본과 AI 생성 말소리가 들립니다. 시연 담당자의 확인 의견입니다.'},
 {name:'missed',file:'bark_tts_0.4.wav',label:'uncertain',
  note:'같은 짖음 원본이지만 말소리가 커서 모델이 놓쳤습니다. 시연 담당자 의견이며 정답 라벨은 아닙니다.'},
 {name:'speech_only',file:'tts_only.wav',label:'other',
  note:'AI 생성 말소리만 넣은 대조 사례입니다. 실제 보호자 의견은 아닙니다.'},
];
const yForLabel={pet_vocalization:151,external_or_tv:199,other:247,uncertain:295};

async function one(browser,item,index){
 const context=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:output,size:{width:1280,height:720}}});
 const page=await context.newPage();page.setDefaultTimeout(12000);
 const errors=[];page.on('pageerror',err=>errors.push(err.message));
 const result={case:item.name,input:item.file,method:'Flutter file input + consent + upload button'};
 try{
  await page.goto('http://127.0.0.1:8024/');
  await page.getByText('연결됨').waitFor();await pause(800);
  await page.getByText('외출 기록·음원 분석으로').click();await pause(650);
  await page.getByText('자동 관찰 · Pi 마이크').click();await pause(200);
  await page.mouse.click(110,435);await pause(180); // Flutter dropdown option: 사용자 음원
  await page.getByRole('button',{name:'외출 시작'}).click();await pause(650);
  await page.getByText('사용자 음원 · 보호자 확인').click();await pause(450);
  await page.locator('input[type=file]').setInputFiles(path.join(output,item.file));
  await page.getByRole('checkbox',{name:'공개·생성 자료 시연용 음원'}).click();
  await page.mouse.move(900,650);await page.mouse.wheel(0,380);await pause(300);
  await page.mouse.click(260,342);
  await page.keyboard.insertText(item.source || (item.name==='speech_only'
    ? 'Gemini 3.8 TTS 말소리만 · 합성 대조 시연'
    : 'FSD50K #15791 짖음 + Gemini 3.8 TTS 말소리 · 합성 시연'));
  await page.getByRole('checkbox',{name:'시연용 기록으로 음원 저장에 동의'}).click();
  await page.screenshot({path:path.join(output,`${index}_upload_form.png`)});await pause(3500);
  const uploadWaiting=page.waitForResponse(r=>r.url().includes('/audio-clips/upload')&&r.request().method()==='POST',{timeout:70000});
  await page.getByRole('button',{name:'음원 업로드·분석'}).click();
  const uploaded=await uploadWaiting;
  if(visitor && new URL(uploaded.url()).host!=='127.0.0.1:8013')throw new Error(`Wrong demo API: ${uploaded.url()}`);
  if(uploaded.status()!==201)throw new Error(`Upload HTTP ${uploaded.status()}: ${(await uploaded.text()).slice(0,300)}`);
  const clip=await uploaded.json();
  result.clip_id=clip.id;result.observation_id=clip.observation_id;
  result.model_score=clip.analysis.audio_lstm.dog_score;
  result.model_name=clip.analysis.audio_lstm.checkpoint_name;
  result.model_windows=clip.analysis.audio_lstm.windows;
  result.detected=result.model_score>=clip.analysis.audio_lstm.threshold;
  await pause(850);
  await page.mouse.move(900,640);await page.mouse.wheel(0,320);await pause(400);
  await page.screenshot({path:path.join(output,`${index}_model_result.png`)});await pause(4000);

  if(item.label){
  await page.getByRole('button',{name:'확인 의견'}).first().click();await pause(350);
  if(item.label!=='uncertain'){
   await page.mouse.click(710,296);await pause(150);
   await page.mouse.click(520,yForLabel[item.label]);await pause(220);
  }
  await page.mouse.click(550,344);
  await page.keyboard.insertText(item.note);
  await page.screenshot({path:path.join(output,`${index}_review_form.png`)});await pause(3000);
  const reviewWaiting=page.waitForResponse(r=>r.url().includes(`/audio-clips/${clip.id}/review`)&&r.request().method()==='POST');
  await page.getByRole('button',{name:'의견 저장'}).click();
  const reviewed=await reviewWaiting;if(reviewed.status()!==200)throw new Error(`Review HTTP ${reviewed.status()}`);
  result.review=(await reviewed.json()).review;
  await pause(600);
  }
  await page.mouse.move(900,350);await page.mouse.wheel(0,-2200);await pause(450);
  await page.getByRole('button',{name:'귀가 · 외출 종료'}).click();await pause(850);
  await page.getByText('사용자 음원 · 보호자 확인').click();await pause(350);
  await page.mouse.move(900,620);await page.mouse.wheel(0,850);await pause(450);
  const question=page.locator('input[aria-label="외출 기록에 질문하기"]');
  await question.fill(visitor
    ? '초인종과 노크 뒤 개 짖음 소리 후보가 나타났나요? 어떤 근거가 있고 실제 방문자 때문에 짖었다고 단정할 수 있나요?'
    : '이번 외출의 개 짖음 소리 후보와 시연 담당자 의견을 알려줘.');
  const ragWaiting=page.waitForResponse(r=>r.url().includes('/explain')&&r.request().method()==='POST',{timeout:70000});
  await page.getByRole('button',{name:'근거 기반 요약'}).click();
  const rag=await ragWaiting;if(rag.status()!==200)throw new Error(`RAG HTTP ${rag.status()}`);
  if(visitor && new URL(rag.url()).host!=='127.0.0.1:8013')throw new Error(`Wrong RAG API: ${rag.url()}`);
  const answer=await rag.json();
  result.rag={provider:answer.provider,failure:answer.failure,retrieval_mode:answer.retrieval_mode,
   claims:answer.claims.map(c=>({id:c.id,text:c.text,observation_ids:c.observation_ids})),
   next_steps:answer.next_steps,answer:answer.answer};
  await pause(700);await page.mouse.move(900,350);await page.mouse.wheel(0,-550);await pause(500);
  await page.screenshot({path:path.join(output,`${index}_rag_header.png`)});await pause(3000);
  await page.mouse.wheel(0,530);await pause(650);
  await page.screenshot({path:path.join(output,`${index}_rag_result.png`)});await pause(4000);
  if(!answer.next_steps?.length)throw new Error('Grounded next-check guidance missing');
  if(visitor){
   if(!answer.claims.some(c=>c.id===`scene.${clip.observation_id}`))throw new Error('Visitor source note missing from RAG claims');
   if(!answer.claims.some(c=>c.id==='current.audio_lstm'))throw new Error('Audio LSTM evidence missing from RAG claims');
  }
  await page.mouse.wheel(0,260);await pause(600);
  await page.screenshot({path:path.join(output,`${index}_rag_guidance.png`)});await pause(4500);
  if(!visitor){
  await page.getByRole('button',{name:`제안 근거 #${clip.observation_id}`}).click();
  await page.getByText(`관찰 #${clip.observation_id} · 원본 근거`).waitFor();
  await page.screenshot({path:path.join(output,`${index}_guidance_evidence.png`)});await pause(3500);
  await page.getByRole('button',{name:'닫기'}).click();await pause(400);
  await page.mouse.click(643,76);await pause(1800);
  const careQuestion=page.locator('input[aria-label="기록에 대해 질문하기"]');
  await careQuestion.fill('이번 음성 LSTM 결과와 시연 담당자 의견을 근거로 다음에 무엇을 확인해야 하나요?');
  await page.screenshot({path:path.join(output,`${index}_care_question.png`)});await pause(2500);
  const careWaiting=page.waitForResponse(r=>r.url().includes('/care/evaluate')&&r.request().method()==='POST',{timeout:70000});
  await page.getByRole('button',{name:'현재 상태 평가하기'}).click();
  const careResponse=await careWaiting;
  if(careResponse.status()!==200)throw new Error(`Care HTTP ${careResponse.status()}: ${(await careResponse.text()).slice(0,250)}`);
  const care=await careResponse.json();
  if(care.observation_id!==clip.observation_id)throw new Error(`Care used observation #${care.observation_id}, expected #${clip.observation_id}`);
  if(care.retrieval?.current_audio?.observation_id!==clip.observation_id)throw new Error('Care missing current audio evidence');
  result.care={provider:care.provider,summary:care.summary,reasons:care.reasons,
   current_audio:care.retrieval.current_audio,provider_failure:care.retrieval.provider_failure||null,
   cited_observation_ids:care.cited_observation_ids};
  await pause(1000);await page.screenshot({path:path.join(output,`${index}_care_summary.png`)});await pause(5500);
  await page.mouse.move(900,600);await page.mouse.wheel(0,540);await pause(650);
  await page.screenshot({path:path.join(output,`${index}_care_evidence.png`)});await pause(5000);
  }
  if(!answer.provider.startsWith('gemini:gemini-3.5-flash-lite'))throw new Error(`Gemini fallback: ${answer.provider}, ${answer.failure}`);
  if(errors.length)throw new Error(`Browser: ${errors.join('; ')}`);
 }catch(err){result.error=String(err);await page.screenshot({path:path.join(output,`${index}_error.png`)});}
 finally{
  const video=page.video();await context.close();
  if(video){const previous=await video.path();const target=path.join(output,`${index}_${item.name}_ui.webm`);fs.renameSync(previous,target);result.video=target;}
 }
 return result;
}

(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const results=[];
 try{for(const [index,item] of cases.entries()){const result=await one(browser,item,index+1);results.push(result);console.log(JSON.stringify({case:result.case,score:result.model_score,provider:result.rag?.provider,error:result.error}));if(result.error)break;}}
  finally{await browser.close();fs.writeFileSync(path.join(output,visitor?'visitor_ui_result.json':'ui_case_results.json'),JSON.stringify(results,null,2));}
 if(results.length!==cases.length||results.some(r=>r.error))process.exitCode=1;
})();
