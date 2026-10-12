// Continuous Edge capture of the preloaded AI-TTS/public-audio demonstration.
// The seed script performs the API upload; this script exercises the actual UI.
const path=require('path');
const {chromium}=require('playwright');
const output=path.resolve('artifacts/ai_sound_demo_20261012');
const pause=ms=>new Promise(r=>setTimeout(r,ms));

(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:output,size:{width:1280,height:720}}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(10000);
 try{
  await page.goto('http://127.0.0.1:8023/');await page.getByText('연결됨').waitFor();await pause(1500);
  await page.getByText('외출 기록·음원 분석으로').click();await pause(1500);
  await page.getByText('사용자 음원 · 보호자 확인').click();await pause(700);
  await page.mouse.move(760,620);
  for(let i=0;i<5;i++){await page.mouse.wheel(0,480);await pause(900);}
  await page.screenshot({path:path.join(output,'review_scrolled.png')});
  console.log('REVIEW', (await page.locator('body').innerText()).slice(0,1000));
  for(let i=0;i<5;i++){await page.mouse.wheel(0,-480);await pause(220);}
  await page.getByText('귀가 · 외출 종료').click();await pause(1400);
  await page.mouse.move(760,620);
  for(let i=0;i<4;i++){await page.mouse.wheel(0,470);await pause(420);}
  await page.getByText('근거 기반 요약').click();await pause(1600);
  await page.screenshot({path:path.join(output,'rag_ui_video.png')});
  console.log('RAG',(await page.locator('body').innerText()).slice(-1800));
  await pause(1800);
  await page.getByRole('checkbox',{name:'RAG·케어'}).click();await pause(1100);
  await page.getByText('현재 상태 평가하기').click();await pause(1800);
  await page.screenshot({path:path.join(output,'care_ui_video.png')});
  console.log('CARE',(await page.locator('body').innerText()).slice(-1300));
  await pause(2200);
  if(errors.length)throw new Error(errors.join('; '));
 }catch(e){
  console.error('VIDEO_ERROR',e);console.error((await page.locator('body').innerText()).slice(-2200));
  await page.screenshot({path:path.join(output,'review_video_error.png')});process.exitCode=1;
 }finally{const video=page.video();await context.close();if(video)console.log('VIDEO',await video.path());await browser.close();}
})();
