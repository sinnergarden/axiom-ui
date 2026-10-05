/* Static display interactions. Values and causal links are saved Owner facts. */
window.createAxiomInteractions = function(env) {
  'use strict';
  const {state,$,current,byId,node,saved,present,percent,money,priceUnit,quantityUnit,statusLabel,renderHeader,renderPoint,selectEvent}=env;
  const cache=new WeakMap(), instances=new Map(), sessionsByChart=new Map(), tickCache=new WeakMap(), bindings=new Map();
  let zoomFrame=0,syncing=false;
  const esc=value=>String(saved(value)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=value=>present(value)&&Number.isFinite(Number(value))?Number(value):null;
  const compact=value=>{const text=saved(value),match=String(text).match(/^([+-]?\d+\.)(\d{7,})$/);return match?(/[1-9]/.test(match[2].slice(6))?'≈':'')+match[1]+match[2].slice(0,6):text;};
  const securityCode=id=>(String(id || '').match(/(?:^|\.)(\d{6})(?:\.|$)/) || [null,id])[1] || '未提供';
  const securityLabel=(v,id)=>v.market.security_labels?.[id] ? v.market.security_labels[id]+' · '+securityCode(id) : securityCode(id)+' · 名称未提供';
  const benchmarkNames={CSI300:'沪深300',SSE_COMPOSITE:'上证综指',NASDAQ100:'纳斯达克100'};
  function benchmark(v){
    const key=state.benchmarkKey || 'CSI300',comparison=v.evaluation?.benchmark_comparisons?.[key];
    if(!comparison)return {key,name:benchmarkNames[key],...(key==='CSI300'?v.evaluation?.benchmark || {}:{status:'SOURCE_UNAVAILABLE',series:[]})};
    const old=new Map((key==='CSI300'?v.evaluation?.benchmark?.series || []:[]).map(p=>[p.session,p]));
    return {...comparison,key,name:benchmarkNames[key],series:comparison.series.map(p=>({...p,session:p.account_session,nav_index:p.normalized_index,drawdown:old.get(p.account_session)?.drawdown,valid:present(p.normalized_index)}))};
  }
  function indexed(v){
    if(cache.has(v))return cache.get(v);
    const rows=v.market.data_batch?.records || v.market.native_chart?.records || v.market.rows || [];
    const securities=new Map(),nav=new Map((v.run.nav || []).map(r=>[r.session,r])),dd=new Map((v.evaluation?.series || []).map(r=>[r.session,r]));
    for(const row of rows){if(!securities.has(row.security_id))securities.set(row.security_id,[]);securities.get(row.security_id).push(row);}
    for(const points of securities.values())points.sort((a,b)=>a.session.localeCompare(b.session));
    const ordersByIntent=new Map(),fillsByOrder=new Map();
    for(const order of v.run.orders || []){if(!ordersByIntent.has(order.intent_id))ordersByIntent.set(order.intent_id,[]);ordersByIntent.get(order.intent_id).push(order);}
    for(const fill of v.run.fills || []){if(!fillsByOrder.has(fill.order_id))fillsByOrder.set(fill.order_id,[]);fillsByOrder.get(fill.order_id).push(fill);}
    const assignedOrders=new Set(),assignedFills=new Set();
    const batches=(v.run.decisions || []).map((decision,index)=>{
      const items=(decision.intents || []).map(intent=>{
        const orders=intent.intent_id?ordersByIntent.get(intent.intent_id) || []:[];
        const fills=orders.flatMap(order=>order.order_id?fillsByOrder.get(order.order_id) || []:[]);
        orders.forEach(o=>assignedOrders.add(o));fills.forEach(f=>assignedFills.add(f));
        return {security_id:intent.security_id,intent,orders,fills};
      });
      const selected=[...(decision.selected_security_ids || []),decision.selected_security_id].filter(Boolean);
      for(const id of selected)if(!items.some(i=>i.security_id===id))items.push({security_id:id,intent:null,orders:[],fills:[]});
      return {key:'decision-'+index,day:decision.trade_session || decision.session,decision,items,linked:true};
    });
    for(const order of v.run.orders || [])if(!assignedOrders.has(order)){
      const fills=order.order_id?fillsByOrder.get(order.order_id) || []:[];fills.forEach(f=>assignedFills.add(f));
      batches.push({key:'unlinked-order-'+batches.length,day:order.session,decision:null,linked:false,items:[{security_id:order.security_id,intent:null,orders:[order],fills}]});
    }
    for(const fill of v.run.fills || [])if(!assignedFills.has(fill))batches.push({key:'unlinked-fill-'+batches.length,day:fill.session,decision:null,linked:false,items:[{security_id:fill.security_id,intent:null,orders:[],fills:[fill]}]});
    batches.sort((a,b)=>(a.day || '').localeCompare(b.day || '') || a.key.localeCompare(b.key));
    const displaySecurities=new Map();for(const row of v.market.review_display?.records || []){if(!displaySecurities.has(row.security_id))displaySecurities.set(row.security_id,[]);displaySecurities.get(row.security_id).push(row);}for(const points of displaySecurities.values())points.sort((a,b)=>a.session.localeCompare(b.session));
    const result={rows,securities,displaySecurities,nav,dd,batches};cache.set(v,result);return result;
  }
  function windowFor(sessions){
    const first=sessions[0] || '',last=sessions.at(-1) || '',w=state.tradeWindow;
    if(w.mode==='custom')return {start:w.start || first,end:w.end || last};
    if(w.mode==='all' || !last)return {start:first,end:last};
    const d=new Date(last+'T12:00:00Z');d.setUTCMonth(d.getUTCMonth()-Number(w.mode));
    return {start:d.toISOString().slice(0,10),end:last};
  }
  function zoomIndices(sessions,window){
    let start=sessions.findIndex(s=>s>=window.start),end=sessions.findLastIndex(s=>s<=window.end);
    if(start<0)start=sessions.length-1;if(end<0)end=0;
    return [start,Math.max(start,end)];
  }
  function controls(v){
    const sessions=[...indexed(v).nav.keys()],window=windowFor(sessions);
    for(const prefix of ['', 'performance-']){
      $(prefix+'trade-window').value=state.tradeWindow.mode;
      for(const [id,value] of [['window-start',window.start],['window-end',window.end]]){
        $(prefix+id).value=value;$(prefix+id).min=sessions[0] || '';$(prefix+id).max=sessions.at(-1) || '';
      }
    }
    const visible=sessions.filter(s=>s>=window.start&&s<=window.end).length;
    for(const id of ['window-note','performance-window-note'])$(id).textContent='显示 '+window.start+' — '+window.end+' · '+visible+' 个账户保存日；指标仍属原回测范围。'+(window.start>window.end?' 起止日期无效。':'');
    $('selection-context').textContent=(state.session?'已锁定 '+state.session+' · ':'')+'窗口 '+window.start+' — '+window.end+'；指标仍为原报告范围。';
    $('unlock-point').disabled=!state.session;
  }
  function setWindow(start,end,sourceId=null){
    if(!start || !end || start>end)return;
    state.tradeWindow={mode:'custom',start,end};state.interval={start,end};state.chainPage=0;
    controls(current());renderHeader(current());
    syncing=true;
    for(const [id,chart] of instances){const ss=sessionsByChart.get(id);if(id===sourceId||!ss?.length)continue;const [a,b]=zoomIndices(ss,{start,end});chart.dispatchAction({type:'dataZoom',startValue:a,endValue:b});}
    syncing=false;renderChain(current());
  }
  function fromZoom(id,event){
    if(syncing)return;
    cancelAnimationFrame(zoomFrame);
    zoomFrame=requestAnimationFrame(()=>{
      const chart=instances.get(id),ss=sessionsByChart.get(id),zoom=event?.batch?.[0] || event || chart.getOption().dataZoom[0];
      const a=typeof zoom.startValue==='number'?zoom.startValue:Math.round(zoom.start/100*(ss.length-1));
      const b=typeof zoom.endValue==='number'?zoom.endValue:Math.round(zoom.end/100*(ss.length-1));
      setWindow(ss[Math.max(0,a)],ss[Math.min(ss.length-1,b)],id);
    });
  }
  function chart(id,option,sessions,onLock){
    const element=$(id);let item=instances.get(id);
    if(!element.offsetWidth){element.dataset.chartReady='pending';return null;}
    if(!item){element.replaceChildren();item=echarts.init(element,null,{renderer:'canvas'});instances.set(id,item);}
    sessionsByChart.set(id,sessions);
    // Remove only our handlers; clearing ZRender's mousemove listeners would
    // detach the library's axis tooltip after a run or tab switch.
    for(const [target,event,handler] of bindings.get(id) || [])target.off(event,handler);
    const registered=[],listen=(target,event,handler)=>{target.on(event,handler);registered.push([target,event,handler]);};
    let down=null,dragged=false,clickedFill=null,clickedReview=null;
    listen(item.getZr(),'mousedown',e=>{down=[e.offsetX,e.offsetY];dragged=false;});
    listen(item.getZr(),'mousemove',e=>{if(down&&Math.hypot(e.offsetX-down[0],e.offsetY-down[1])>5)dragged=true;});
    listen(item,'click',p=>{if(p.seriesId==='fills')clickedFill=p.data.fill;else if(p.seriesId==='review-events')clickedReview=p.data;});
    listen(item.getZr(),'click',e=>{
      queueMicrotask(()=>{
        const fill=clickedFill,review=clickedReview;clickedFill=null;clickedReview=null;down=null;
        if(dragged){dragged=false;return;}
        if(review){onLock(review.day);openRaw('Data 保存发行人事件 · 不代表账户已应用',review.reviewEvent);return;}
        if(!item.containPixel({gridIndex:0},[e.offsetX,e.offsetY])&&!item.containPixel({gridIndex:1},[e.offsetX,e.offsetY]))return;
        const raw=item.convertFromPixel({xAxisIndex:0},e.offsetX),index=Math.max(0,Math.min(sessions.length-1,Math.round(raw)));
        if(sessions[index])onLock(sessions[index],fill);
      });
    });
    item.setOption(option,{notMerge:true,lazyUpdate:false});
    listen(item,'datazoom',event=>fromZoom(id,event));bindings.set(id,registered);element.dataset.pointCount=sessions.length;
    element.dataset.chartVendor='Apache ECharts 6.1.0';element.dataset.chartReady='true';
    item.resize();return item;
  }
  function emptyChart(id,message){
    const old=instances.get(id);if(old){old.dispose();instances.delete(id);}sessionsByChart.delete(id);$(id).replaceChildren(node('p',message,'missing'));$(id).dataset.chartReady='false';
  }
  const dateTick=(session,index,sessions)=>{
    const key=JSON.stringify(state.tradeWindow);let savedRange=tickCache.get(sessions);
    if(savedRange?.key!==key){const window=windowFor(sessions),indices=zoomIndices(sessions,window);savedRange={key,count:indices[1]-indices[0]+1};tickCache.set(sessions,savedRange);}
    return savedRange.count>500?session.slice(0,4):savedRange.count>70?session.slice(0,7):session.slice(5);
  };
  function dateInterval(index,session,sessions){
    dateTick(session,index,sessions);const count=tickCache.get(sessions).count;
    const previous=sessions[index-1];return count>500?!previous||session.slice(0,4)!==previous.slice(0,4):count>70?!previous||session.slice(0,7)!==previous.slice(0,7):true;
  }
  function axes(sessions,priceLabel,ddLabel){
    return {grid:[{left:68,right:22,top:42,height:'48%'},{left:68,right:22,top:'66%',height:'15%'}],
      xAxis:[0,1].map(i=>({type:'category',gridIndex:i,data:sessions,boundaryGap:false,axisLine:{lineStyle:{color:'#b8c6d3'}},axisTick:{show:false},axisLabel:{show:i===1,hideOverlap:true,color:'#53687c',interval:(index,s)=>dateInterval(index,s,sessions),formatter:(s,index)=>dateTick(s,index,sessions)},axisPointer:{show:true,snap:true,label:{show:true}}})),
      yAxis:[{type:'value',name:priceLabel,scale:true,splitNumber:5,nameLocation:'end',nameTextStyle:{color:'#53687c'},axisLabel:{color:'#53687c'},splitLine:{show:state.grid,lineStyle:{color:'#edf1f5'}}},{type:'value',gridIndex:1,name:ddLabel,scale:true,splitNumber:3,nameTextStyle:{color:'#53687c'},axisLabel:{color:'#53687c'},splitLine:{show:state.grid,lineStyle:{color:'#edf1f5'}}}],
      axisPointer:{link:[{xAxisIndex:'all'}],snap:true,lineStyle:{color:'#607d98',type:'dashed'},animation:false},
      dataZoom:zoomOptions(sessions)};
  }
  function zoomOptions(sessions){
    const [a,b]=zoomIndices(sessions,windowFor(sessions));
    return [{type:'inside',xAxisIndex:[0,1],startValue:a,endValue:b,filterMode:'filter',zoomOnMouseWheel:'ctrl',moveOnMouseMove:true,moveOnMouseWheel:false,preventDefaultMouseMove:true},
      {type:'slider',xAxisIndex:[0,1],left:68,right:22,bottom:8,height:27,startValue:a,endValue:b,showDataShadow:true,brushSelect:false,filterMode:'filter',borderColor:'#d9e2eb',backgroundColor:'#f4f7fa',fillerColor:'#dbe6f066',handleSize:'90%',textStyle:{color:'#53687c'},labelFormatter:value=>sessions[Math.round(value)] || ''}];
  }
  function tooltipRows(day,rows){
    return '<div class="hover-card"><strong>'+esc(day)+'</strong>'+rows.map(([label,value])=>'<div><span>'+esc(label)+'</span><b title="'+esc(value)+'">'+esc(compact(value))+'</b></div>').join('')+'</div>';
  }
  function readDay(v,day){
    const index=indexed(v),nav=index.nav.get(day),dd=index.dd.get(day);
    const b=benchmark(v),bench=(b.series || []).find(r=>r.session===day),other=byId.get(state.compare),old=other?indexed(other).nav.get(day):null;
    const analysis=v.evaluation?.analysis_series?.find(p=>p.session===day);
    return [['策略净值指数',nav?.nav_index],...(analysis?[['策略累计收益',percent(analysis.account_cumulative_return)]]:[]),...(state.benchmark?[[b.name+'归一化指数',bench?.valid===false?null:bench?.nav_index],[b.name+'回撤',bench?.valid===false||!present(bench?.drawdown)?'未提供':percent(bench.drawdown)]]:[]),['策略回撤',present(dd?.drawdown)?percent(dd.drawdown):'未提供'],['净资产（元）',nav?money(nav.nav_minor):'未提供'],...(other?[['对照净值指数',old?.nav_index]]:[])];
  }
  function lockDay(day,fill=null){
    const v=current();state.session=fill?.session || day;state.fillId=fill?.fill_id || '';state.eventId=state.fillId;state.kind='fills';state.chainPage=0;
    if(fill){state.security=fill.security_id;state.chainSecurity=fill.security_id;}
    else if(state.pane==='trade')state.chainSecurity=state.security;
    renderHeader(v);controls(v);selection(v);renderChain(v);
    if(fill)renderPoint(v,fill,'fills');else if(state.pane==='trade')renderPoint(v);
    $('nav-point').textContent='已锁定 '+state.session+' · '+readDay(v,state.session).map(([label,value])=>label+' '+compact(value)).join(' / ');
  }
  function selection(v){
    for(const [id,item] of instances){
      if(!['performance-chart','trade-chart'].includes(id))continue;
      const primary=id==='performance-chart'?'account':'prices',ss=sessionsByChart.get(id);
      const lines=state.session&&ss.includes(state.session)?[{xAxis:state.session}]:[],recovery=v.evaluation?.drawdown_interval?.recovery_session;
      if(id==='performance-chart'&&recovery&&ss.includes(recovery))lines.push({xAxis:recovery,name:'恢复日',lineStyle:{color:'#538772',type:'dotted'},label:{show:true,formatter:'恢复日'}});
      item.setOption({series:[{id:primary,markLine:{silent:true,symbol:'none',lineStyle:{color:'#537c9e',type:'dashed',width:1},label:{show:false},data:lines}}]});
    }
  }
  function performance(v){
    const index=indexed(v),nav=v.run.nav || [],b=benchmark(v),other=byId.get(state.compare);
    if(!nav.length){emptyChart('performance-chart','账户净值未载入，不从信号生成收益。');return;}
    const ss=[...new Set([...nav.map(r=>r.session),...(state.benchmark?b.series || []:[]).map(r=>r.session),...(other?.run.nav || []).map(r=>r.session)])].sort();
    const mapSeries=(rows,field)=>{const map=new Map((rows || []).map(r=>[r.session,r]));return ss.map(s=>{const r=map.get(s);return r?.valid===false?null:number(r?.[field]);});};
    const series=[{id:'account',name:'策略净值指数',type:'line',showSymbol:false,data:mapSeries(nav,'nav_index'),lineStyle:{width:2,color:'#477a9e'},itemStyle:{color:'#477a9e'},connectNulls:false},
      {id:'drawdown',name:'策略回撤',type:'line',xAxisIndex:1,yAxisIndex:1,showSymbol:false,data:mapSeries(v.evaluation?.series,'drawdown'),lineStyle:{width:1.4,color:'#578471'},areaStyle:{color:'#dcebe3',opacity:.65},itemStyle:{color:'#578471'},connectNulls:false}];
    if(state.benchmark&&b.status!=='SOURCE_UNAVAILABLE'){series.push({id:'benchmark',name:b.name,type:'line',showSymbol:false,data:mapSeries(b.series,'nav_index'),lineStyle:{type:'dashed',width:1.5,color:'#a88948'},itemStyle:{color:'#a88948'},connectNulls:false});if(b.series.some(p=>present(p.drawdown)))series.push({id:'benchmark-dd',name:'基准回撤',type:'line',xAxisIndex:1,yAxisIndex:1,showSymbol:false,data:mapSeries(b.series,'drawdown'),lineStyle:{type:'dashed',color:'#a88948',width:1},connectNulls:false});}
    const dd=v.evaluation?.drawdown_interval,available=dd?.status==='AVAILABLE';
    $('locate-drawdown').disabled=!available;$('locate-drawdown').textContent=available?'定位最大回撤':dd?.status==='NO_DRAWDOWN'?'没有负回撤':'定位最大回撤 · 日期待提供';
    if(available){const start=ss.includes(dd.peak_session)?dd.peak_session:ss[0];series[0].markArea={silent:true,itemStyle:{color:'#e8d3d9',opacity:.23},data:[[{xAxis:start},{xAxis:dd.trough_session}]]};series[1].markArea={silent:true,itemStyle:{color:'#e8d3d9',opacity:.23},data:[[{xAxis:start},{xAxis:dd.trough_session}]]};if(dd.recovery_session)series[0].markLine={silent:true,symbol:'none',lineStyle:{color:'#538772',type:'dotted'},data:[{xAxis:dd.recovery_session,name:'恢复日'}]};}
    if(other){series.push({id:'comparison',name:'旧运行',type:'line',showSymbol:false,data:mapSeries(other.run.nav,'nav_index'),lineStyle:{type:'dashed',color:'#8d709c',width:1.5},itemStyle:{color:'#8d709c'},connectNulls:false});series.push({id:'comparison-dd',name:'对照回撤',type:'line',xAxisIndex:1,yAxisIndex:1,showSymbol:false,data:mapSeries(other.evaluation?.series,'drawdown'),lineStyle:{type:'dashed',color:'#8d709c',width:1},connectNulls:false});}
    const base=axes(ss,'净值指数','回撤（%）');base.yAxis[1].axisLabel.formatter=value=>percent(String(value));
    chart('performance-chart',{...base,animation:false,legend:{top:5,right:22,textStyle:{fontSize:12,color:'#52677c'},data:series.filter(s=>s.yAxisIndex!==1).map(s=>s.name)},tooltip:{trigger:'axis',triggerOn:'mousemove',confine:true,transitionDuration:0,axisPointer:{type:'cross'},formatter:items=>{
      const day=items[0]?.axisValue;if(!day)return '';const rows=readDay(v,day);
      if(!state.session)$('nav-point').textContent=day+' · '+rows.map(([k,val])=>k+' '+compact(val)).join(' / ');
      return tooltipRows(day,rows);
    }},series},ss,lockDay);
    if(state.session)$('nav-point').textContent='已锁定 '+state.session+' · '+readDay(v,state.session).map(([k,val])=>k+' '+compact(val)).join(' / ');
    else $('nav-point').textContent='在图内任意位置移动查看同日原值；点击锁定。拖动平移，Ctrl+滚轮缩放，也可拖动下方时间概览。';
    controls(v);selection(v);analysis(v);
  }
  function trade(v){
    const index=indexed(v),ids=[...new Set([...index.securities.keys(),...index.displaySecurities.keys()])].sort(),select=$('security-select');
    if(!ids.includes(state.security))state.security=ids[0] || '';
    select.replaceChildren();for(const id of ids){const option=node('option',securityLabel(v,id));option.value=id;select.append(option);}select.value=state.security;
    $('trade-security-title').textContent=securityLabel(v,state.security);
    $('session-select').value=state.session;
    const display=v.market.review_display,choice=$('price-basis-select');state.priceBasisByRun ||= {};
    const adjusted=!!display&&(state.priceBasisByRun[v.run.run_id] || 'adjusted')==='adjusted';
    choice.options[1].disabled=!display;choice.options[1].textContent=display?'共同最终锚点调整价':'调整后 · 尚未提供';choice.value=adjusted?'adjusted':'unadjusted';
    const displayPoints=index.displaySecurities.get(state.security),points=displayPoints?(adjusted?displayPoints:displayPoints.map(p=>({...p,open:p.native_open,high:p.native_high,low:p.native_low,close:p.native_close}))):index.securities.get(state.security) || [],ss=points.map(p=>p.session),window=windowFor(ss),pointByDay=new Map(points.map(p=>[p.session,p]));
    const candle=!!(v.market.data_batch || v.market.native_chart),volume=env.stockAccount(v)?'volume_shares':'volume_units';
    $('candle-note').textContent=(candle?'':'K线暂未提供，当前仅显示保存的收盘价与全天量。')+(display?(adjusted?'共同最终锚点调整价':'同一显示来源的未复权原价')+' · 固定 A='+display.context.anchor_session+' / C='+display.context.knowledge_cutoff+'；缩放不改变锚点。'+(adjusted?' 成交调整坐标尚未提供，暂不放置 B/S；原成交可在交易链查看。':' B/S 使用保存的原成交价。'):'调整后显示投影尚未提供；下方为保存的未复权'+(candle?' K 线':'收盘价线（非 K 线）')+'。B/S 是保存模拟成交，悬浮卡保留原成交价。')+'价格 '+priceUnit(v)+'，全天量 '+quantityUnit(v)+'。'+(v.market.security_name_scope?' 名称为 Snapshot 标签，历史名称有效期未知。':'');
    const fills=(v.run.fills || []).filter(f=>f.security_id===state.security),fillByDay=new Map();
    for(const fill of fills){if(!fillByDay.has(fill.session))fillByDay.set(fill.session,[]);fillByDay.get(fill.session).push(fill);}
    const reviewEvents=(v.market.review_events || []).filter(r=>r.event.security_id===state.security).map(item=>({item,day:item.domain==='corporate_actions'?item.event.ex_date:item.event.effective_date,label:item.domain==='corporate_actions'?'除息':'份额折算'}));
    if(!points.length){emptyChart('trade-chart','证券行情未提供，不构造 K 线。');renderChain(v);return;}
    const base=axes(ss,'价格（'+priceUnit(v)+'）','全天量（'+quantityUnit(v)+'）');
    base.yAxis[1].axisLabel.formatter=value=>Math.abs(value)>=100000000?(value/100000000).toFixed(1)+'亿':Math.abs(value)>=10000?(value/10000).toFixed(0)+'万':String(value);
    base.xAxis.forEach(axis=>axis.boundaryGap=true);
    const prices=candle?{id:'prices',name:adjusted?'共同锚点调整 K 线':'未复权 K 线',type:'candlestick',data:points.map(p=>['open','close','low','high'].every(k=>number(p[k])!==null)?[number(p.open),number(p.close),number(p.low),number(p.high)]:null),itemStyle:{color:'#be7387',color0:'#548976',borderColor:'#be7387',borderColor0:'#548976'}}:
      {id:'prices',name:'保存收盘价（非 K 线）',type:'line',showSymbol:false,data:points.map(p=>number(p.close)),itemStyle:{color:'#547da3'},connectNulls:false};
    prices.markArea={silent:true,itemStyle:{color:'#dde7ef',opacity:.26},data:(v.evaluation?.episodes || []).filter(e=>e.security_id===state.security).map(e=>[{xAxis:e.entry_session || ss[0],itemStyle:{borderType:e.status==='OPEN'?'dashed':'solid'}},{xAxis:e.exit_session || ss.at(-1)}])};
    const series=[prices,{id:'volume',name:'全天量',type:'bar',xAxisIndex:1,yAxisIndex:1,data:points.map(p=>number(p[volume] ?? p.volume)),itemStyle:{color:'#b8c9d7'},barMaxWidth:12},
      {id:'fills',name:'保存成交',type:'scatter',data:(adjusted?[]:fills).map(fill=>({value:[fill.session,number(fill.price)],fill,symbol:fill.side==='BUY'?'triangle':'diamond',symbolSize:fill.fill_id===state.fillId?22:15,label:{show:true,position:fill.side==='BUY'?'bottom':'top',formatter:fill.side==='BUY'?'B':'S',color:fill.side==='BUY'?'#ad4f6a':'#31795e',fontSize:11},itemStyle:{color:fill.side==='BUY'?'#ad4f6a':'#31795e',borderColor:'white',borderWidth:1}}))}];
    series.push({id:'review-events',name:'发行人事件（非成交）',type:'scatter',symbol:'rect',symbolSize:8,symbolOffset:[0,-14],data:reviewEvents.filter(e=>pointByDay.has(e.day)&&present(pointByDay.get(e.day).close)).map(e=>({value:[e.day,number(pointByDay.get(e.day).close)],day:e.day,reviewEvent:e.item,label:{show:true,position:'top',formatter:e.label,color:'#8a713e',fontSize:10},itemStyle:{color:'#ae935e'}}))});
    chart('trade-chart',{...base,animation:false,tooltip:{trigger:'axis',triggerOn:'mousemove',confine:true,transitionDuration:0,axisPointer:{type:'cross'},formatter:items=>{
      const day=items[0]?.axisValue,p=pointByDay.get(day);if(!p)return '';
      return tooltipRows(day,[[securityLabel(v,state.security),adjusted?'共同锚点调整价':'未复权'],...['open','high','low','close'].filter(k=>Object.hasOwn(p,k)).map(k=>[({open:'开盘',high:'最高',low:'最低',close:'收盘'})[k]+'（'+priceUnit(v)+'）',p[k]]),...(adjusted?[['原价收盘',p.native_close],['显示缺失原因',p.display_missing_reason || '无']]:[]),['全天量（'+quantityUnit(v)+'）',p[volume] ?? p.volume],...reviewEvents.filter(e=>e.day===day).map(e=>[e.label+'（发行人）',saved(e.item.event.process_status)]),...(fillByDay.get(day) || []).map(f=>[(f.side==='BUY'?'买入':'卖出')+' '+saved(f.quantity)+quantityUnit(v),'原成交价 '+saved(f.price)+' '+priceUnit(v)+' · 费用 '+money(f.fee_minor)+' 元'])]);
    }},series},ss,lockDay);
    $('trade-chart').dataset.visiblePointCount=points.filter(p=>p.session>=window.start&&p.session<=window.end).length;
    controls(v);selection(v);renderChain(v);
    const facts=$('review-event-list');facts.replaceChildren();$('review-event-context').hidden=!display;
    for(const event of reviewEvents.filter(e=>!e.day||(e.day>=window.start&&e.day<=window.end))){const button=node('button',event.label+' · '+saved(event.day)+' · '+saved(event.item.event.process_status),'fill-chain-item');button.addEventListener('click',()=>openRaw('Data 保存发行人事件 · 不代表账户已应用',event.item));facts.append(button);}
    if(!facts.childElementCount)facts.append(node('p',display?.events_status==='not_requested'?'当前显示导出没有请求事件。':'当前证券及窗口没有保存的除息/折算事件；不推断供应完整。','small'));
    const selected=(v.run[state.kind] || []).find(e=>env.eventKey(e)===state.eventId);
    if(selected)renderPoint(v,selected,state.kind);else if(state.session)renderPoint(v);else{$('trade-point').replaceChildren(node('h3','保存点详情'),node('p','图内移动预览，点击日期或 B/S 锁定；从下方交易链查看保存目标、数量与原因。','small'));}
  }
  function detailRow(parent,label,value){const row=node('div',null,'chain-value');row.append(node('span',label),node('strong',saved(value)));parent.append(row);}
  const reasonLabel=reason=>({RAW_TOP5:'按保存原始分数选择前 5',RAW_TOPK:'按保存原始分数选择前 K',UNKNOWN_MARKET_STATUS:'市场状态缺证',NO_DECISION:'没有新决策，保持原持仓',ANNOUNCED_SUSPENSION:'保存公告全天停牌',SAME_TARGET:'目标未变',ROTATE:'轮动目标变化',INSUFFICIENT_CASH:'现金不足'})[reason] || saved(reason);
  function displayReason(decision){const rows=decision?.trace || [];const reasons=Array.isArray(rows)?rows.map(r=>r.reason).filter(Boolean):[];return reasons.length?reasons.map(reasonLabel).join('；'):decision?.reason?reasonLabel(decision.reason):'买卖原因未保存';}
  function openRaw(label,value){$('raw-title').textContent=label;$('raw-values').textContent=JSON.stringify(value,null,2);$('raw-dialog').showModal();}
  function renderItem(v,batch,item){
    const detail=node('details',null,'chain-security'),id=item.security_id;
    detail.dataset.securityId=id;
    detail.open=state.session===batch.day&&(!state.chainSecurity || state.chainSecurity===id);
    const summary=node('summary',securityLabel(v,id)+' · '+(item.intent?.side==='BUY'?'买入':item.intent?.side==='SELL'?'卖出':'保存目标'));
    detail.append(summary);let loaded=false;
    const load=()=>{
      if(loaded||!detail.open)return;loaded=true;
      const core=node('div',null,'chain-stage');core.append(node('h3','1 · 决策 / 意图'));
      detailRow(core,'信号日 / 决策日',saved(batch.decision?.feature_session)+' / '+saved(batch.day));
      detailRow(core,'状态',batch.decision?statusLabel(batch.decision.status):'决策关联未提供');
      detailRow(core,'保存目标（'+quantityUnit(v)+'）',batch.decision?.targets?.[id]);
      detailRow(core,'买卖原因',displayReason(batch.decision));
      detailRow(core,'意图数量（'+quantityUnit(v)+'）',item.intent?.quantity);
      core.append(node('p','决策完成表示已产生意图，不代表委托已成交。','small'));detail.append(core);
      const runtime=node('div',null,'chain-stage');runtime.append(node('h3','2 · 委托 / 执行依据'));
      if(!item.orders.length)runtime.append(node('p','委托关联未提供。','small'));
      for(const order of item.orders){const box=node('div',null,'order-row');
        detailRow(box,'委托 / 已成交 / 未成交（'+quantityUnit(v)+'）',saved(order.quantity)+' / '+saved(order.filled_quantity)+' / '+saved(order.unfilled_quantity));
        detailRow(box,'状态 / 未成交原因',statusLabel(order.status)+' / '+(order.reason?reasonLabel(order.reason):'未提供'));
        detailRow(box,'原市场状态 / 原因',saved(order.market_state)+' / '+saved(order.state_reason));
        const button=node('button','查看委托原值','text-button');button.addEventListener('click',()=>{selectEvent(v,order,'orders');openRaw('保存委托',order);});box.append(button);runtime.append(box);
      }detail.append(runtime);
      const execution=node('div',null,'chain-stage');execution.append(node('h3','3 · 成交原值'));
      if(!item.fills.length)execution.append(node('p','没有保存成交；图中不添加 B/S。','small'));
      for(const fill of item.fills){const button=node('button',fill.session+' · '+(fill.side==='BUY'?'买入':'卖出')+' '+saved(fill.quantity)+quantityUnit(v)+' × '+saved(fill.price)+priceUnit(v)+' · 费用 '+money(fill.fee_minor)+' 元','fill-chain-item');
        button.dataset.fillId=fill.fill_id;button.classList.toggle('selected',fill.fill_id===state.fillId);button.addEventListener('click',()=>{state.pane='trade';state.security=id;lockDay(fill.session,fill);trade(v);});execution.append(button);
      }detail.append(execution);
      const raw=node('button','查看此证券保存链','text-button');raw.addEventListener('click',()=>openRaw('决策 / 意图 / 委托 / 成交保存链',{decision:batch.decision,intent:item.intent,orders:item.orders,fills:item.fills}));detail.append(raw);
    };detail.addEventListener('toggle',load);load();return detail;
  }
  function renderChain(v){
    const root=$('event-list');root.replaceChildren();
    const ss=[...indexed(v).nav.keys()],window=windowFor(ss),search=($('chain-search').value || '').trim().toLowerCase(),security=state.chainSecurity || '',status=$('chain-status').value;
    const select=$('chain-security');if(select.dataset.run!==v.run.run_id){select.replaceChildren(node('option','全部证券'));select.firstChild.value='';for(const id of indexed(v).securities.keys()){const option=node('option',securityLabel(v,id));option.value=id;select.append(option);}select.dataset.run=v.run.run_id;}select.value=security;
    const groups=indexed(v).batches.filter(b=>b.day>=window.start&&b.day<=window.end).map(batch=>({...batch,items:batch.items.filter(item=>{
      if(security&&item.security_id!==security)return false;
      if(status&&batch.decision?.status!==status&&!item.orders.some(o=>o.status===status))return false;
      const text=[batch.day,item.security_id,securityLabel(v,item.security_id),item.intent?.side,displayReason(batch.decision),...item.orders.flatMap(o=>[o.status,o.reason,o.state_reason])].join(' ').toLowerCase();return !search||text.includes(search);
    })})).filter(b=>b.items.length || (!security&&b.decision?.status==='NO_DECISION'&&(!status||status==='NO_DECISION')&&(!search||[b.day,b.decision.status,'没有新决策',displayReason(b.decision)].join(' ').toLowerCase().includes(search))));
    $('chain-summary').textContent=groups.length+' 条匹配的保存决策/独立执行记录；按真实 intent→order→fill 引用连链，不用同日推断关联。';
    if(!groups.length){root.append(node('p','当前筛选没有保存记录。','small'));return;}
    const years=new Map();for(const batch of groups){const year=batch.day.slice(0,4);if(!years.has(year))years.set(year,[]);years.get(year).push(batch);}
    const focus=state.session || window.end;
    for(const [year,batches] of [...years].reverse()){
      const y=node('details',null,'chain-year');y.append(node('summary',year+' 年 · '+batches.length+' 条保存记录'));y.open=year===focus.slice(0,4);root.append(y);let yearLoaded=false;
      const loadYear=()=>{if(yearLoaded||!y.open)return;yearLoaded=true;const months=new Map();for(const batch of batches){const month=batch.day.slice(0,7);if(!months.has(month))months.set(month,[]);months.get(month).push(batch);}
        for(const [month,records] of [...months].reverse()){
          const m=node('details',null,'chain-month');m.append(node('summary',month+' · '+records.length+' 条'));m.open=month===focus.slice(0,7);y.append(m);let monthLoaded=false;
          const loadMonth=()=>{if(monthLoaded||!m.open)return;monthLoaded=true;let page=0;const content=node('div'),pager=node('div',null,'chain-pager');m.append(content,pager);
            const showPage=()=>{content.replaceChildren();pager.replaceChildren();const size=12,total=Math.ceil(records.length/size);
              for(const batch of records.slice(page*size,(page+1)*size)){
                const d=node('details',null,'chain-batch');d.dataset.batchDay=batch.day;d.append(node('summary',batch.day+' · '+(batch.linked?'保存决策 / 调仓':'独立执行记录 · 决策关联未提供')+' · '+batch.items.length+' 证券'));d.open=batch.day===state.session;content.append(d);let loaded=false;
                const loadBatch=()=>{if(loaded||!d.open)return;loaded=true;const brief=node('p',batch.decision?statusLabel(batch.decision.status)+'；'+displayReason(batch.decision):'仅显示原委托/成交关联；不猜决策原因。','small');d.append(brief);for(const item of batch.items)d.append(renderItem(v,batch,item));if(!batch.items.length)d.append(node('p','保存决策没有意图；保持原值，不据此构造交易。','small'));};d.addEventListener('toggle',loadBatch);loadBatch();
              }
              const prev=node('button','上一页'),next=node('button','下一页');prev.disabled=page===0;next.disabled=page>=total-1;prev.addEventListener('click',()=>{page--;showPage();});next.addEventListener('click',()=>{page++;showPage();});pager.append(prev,node('span',(page+1)+' / '+total+' · 每页 '+size+' 条','small'),next);
            };const target=records.findIndex(b=>b.day===state.session);if(target>=0)page=Math.floor(target/12);showPage();
          };m.addEventListener('toggle',loadMonth);loadMonth();
        }
      };y.addEventListener('toggle',loadYear);loadYear();
    }
  }
  function summaries(v,comparison,differences,unverified){
    const panel=$('configuration-differences');panel.replaceChildren();
    panel.append(node('p',v.research?.version_explanation || '本版本说明未提供。'));
    const changes=v.research?.changes || [];if(changes.length){const ul=node('ul');for(const change of changes)ul.append(node('li',typeof change==='string'?change:Object.entries(change).filter(([,value])=>!value || typeof value!=='object').map(([key,value])=>key+'：'+saved(value)).join(' · ') || '声明详见原始记录'));panel.append(ul);}else panel.append(node('p','未保存显式变动清单；不从收益推测改动。','small'));
    const values=$('configuration-values');values.replaceChildren();
    for(const [label,value] of [['回测范围',saved(v.configuration.start_session)+' — '+saved(v.configuration.end_session)],['初始账户',typeof v.configuration.initial_account==='object'?'见保存初始账户详情':saved(v.configuration.initial_account)],['价格口径',v.configuration.price_basis || v.market.price_basis],['执行假设',env.stockAccount(v)?'股票日线事后近似 / strict 按所选运行':v.approximate?'ETF 日线近似':'保存策略执行条件']])detailRow(values,label,value);
    if(comparison)values.append(node('p','条件差异：'+(differences.join('、') || '未发现保存差异')+(unverified.length?'；未核实 '+unverified.join('、'):''),'small'));
    const raw=node('button','查看输入与版本差异原始记录','text-button');raw.addEventListener('click',()=>openRaw('保存输入与版本差异',{configuration:v.configuration,comparison:comparison?.configuration || null,declared_changes:v.research?.changes,version_comparison:v.research?.version_comparison}));values.append(raw);
  }
  function returnPoints(v){
    const element=$('episode-chart'),episodes=(v.evaluation?.episodes || []).filter(e=>e.statistics_eligible&&e.status==='CLOSED'&&present(e.net_return)),distribution=v.evaluation?.return_distribution;
    $('return-distribution-note').textContent=distribution?'Owner 保存的完整持仓段净收益率 · '+saved(distribution.included_episode_count)+' 段 · 每档 2% · 零点按左闭右开归入 [0%, 2%)。'+(distribution.status==='INSUFFICIENT_SAMPLE'?'样本少于 '+saved(distribution.minimum_episodes)+' 段，只有逐段点，未提供分箱。':'柱高直接读取保存计数，尾部范围见悬浮卡。'):'新百分比分布尚未提供；仅展示 Owner 保存的逐段净收益率，不能称分箱分布。';
    if(!episodes.length){emptyChart('episode-chart','没有保存可统计闭合段收益率，不从金额推算。');return;}
    if(!element.offsetWidth){element.dataset.chartReady='pending';return;}
    let item=instances.get('episode-chart');if(!item){element.replaceChildren();item=echarts.init(element);instances.set('episode-chart',item);}
    item.off('click');
    if(distribution?.status==='AVAILABLE'){
      const bins=distribution.bins,label=b=>!present(b.lower)?'低于 '+percent(b.upper):!present(b.upper)?percent(b.lower)+' 及以上':'['+percent(b.lower)+', '+percent(b.upper)+')';
      item.setOption({animation:false,grid:{left:45,right:16,top:25,bottom:48},xAxis:{type:'category',data:bins.map(label),name:'段净收益率（%）',nameLocation:'middle',nameGap:33,axisTick:{show:false},axisLabel:{interval:0,hideOverlap:true,color:'#53687c',formatter:(value,i)=>i===0?'＜-20%':i===bins.length-1?'≥20%':i%3===2||Number(bins[i].lower)===0?percent(bins[i].lower):''}},yAxis:{type:'value',name:'完整段数',minInterval:1,splitNumber:4,splitLine:{show:true,lineStyle:{color:'#edf1f5'}},axisLabel:{color:'#53687c'}},tooltip:{trigger:'axis',confine:true,formatter:items=>{const p=items[0];return p?tooltipRows('持仓段收益率 · '+label(bins[p.dataIndex]),[['保存段数',bins[p.dataIndex].count],['口径','合格闭合段，等权统计']]):'';}},series:[{id:'saved-return-bins',type:'bar',barMaxWidth:18,data:bins.map(b=>({value:b.count,itemStyle:{color:present(b.upper)&&Number(b.upper)<=0?'#538772':'#b96782'}})),markLine:{silent:true,symbol:'none',lineStyle:{color:'#5e7388',type:'dashed'},label:{show:false},data:[{xAxis:bins.findIndex(b=>present(b.lower)&&Number(b.lower)===0)}]}}]},{notMerge:true});
      element.dataset.chartReady='true';element.dataset.distributionStatus=distribution.status;element.dataset.savedBinCount=bins.length;element.dataset.savedEpisodeCount=distribution.included_episode_count;return;
    }
    element.dataset.distributionStatus=distribution?.status || 'NOT_PROVIDED';delete element.dataset.savedBinCount;
    item.setOption({animation:false,grid:{left:56,right:18,top:26,bottom:40},xAxis:{type:'value',name:'段净收益率（%）',nameLocation:'middle',nameGap:28,min:extent=>Math.min(extent.min,0),max:extent=>Math.max(extent.max,0),axisLabel:{formatter:value=>percent(String(value)),color:'#53687c'},splitLine:{show:false}},yAxis:{type:'value',min:-1,max:5,show:false},tooltip:{confine:true,formatter:p=>tooltipRows(p.data.episode.entry_session+' — '+p.data.episode.exit_session,[[securityLabel(v,p.data.episode.security_id),'完整持仓段'],['净收益率',percent(p.data.episode.net_return)],['净盈亏（元）',money(p.data.episode.net_pnl_minor)]])},series:[{type:'scatter',symbolSize:8,data:episodes.map((episode,i)=>({value:[number(episode.net_return),i%5],episode,itemStyle:{color:number(episode.net_return)<0?'#538772':'#b96782'}})),markLine:{silent:true,symbol:'none',label:{show:false},lineStyle:{color:'#899ead',type:'dashed'},data:[{xAxis:0}]}}]},{notMerge:true});
    item.on('click',p=>{if(p.data?.episode)env.selectEpisode(p.data.episode);});element.dataset.chartReady='true';element.dataset.savedEpisodeCount=episodes.length;
  }
  function analysis(v){
    const evaluation=v.evaluation,comparisons=evaluation?.benchmark_comparisons,select=$('benchmark-select');
    for(const option of select.options){const comparison=comparisons?.[option.value],available=comparison?comparison.status!=='SOURCE_UNAVAILABLE':option.value==='CSI300'&&!!evaluation?.benchmark;option.textContent=benchmarkNames[option.value]+(available?'':' · 未提供');}
    select.value=state.benchmarkKey || 'CSI300';
    const b=benchmark(v);$('benchmark-toggle').disabled=!b.series?.length;$('benchmark-toggle').checked=state.benchmark&&!!b.series?.length;
    if(comparisons){$('benchmark-note').textContent=b.name+' · '+(b.status==='SOURCE_UNAVAILABLE'?'原生输入未提供':b.status==='COMPLETE'?'保存点完整':'部分保存点缺失')+' · 币种 '+saved(b.currency)+' / '+(b.return_basis==='price_index_excluding_dividends'?'价格指数，不含分红':saved(b.return_basis))+' · 原生日历 '+saved(b.native_calendar)+' / 时区 '+saved(b.timezone)+'。按同名自然日期展示，不补齐市场假日、不宣称同一时刻可交易。'+(b.currency&&b.currency!=='CNY'?' 未提供 FX，人民币账户相对财富留空。':'');}
    const panel=$('risk-analysis');panel.replaceChildren();
    if(!evaluation?.risk_metrics){panel.append(node('p','当前保存评价未提供 Sharpe / Calmar、滚动分析或回撤日期；不从旧报告自行计算。','small'));$('analysis-chart').hidden=true;return;}
    const labels={INSUFFICIENT_SPAN:'范围不足一年',INSUFFICIENT_OBSERVATIONS:'观测少于 30 个',MISSING_RETURN:'收益观测缺失',ZERO_VOLATILITY:'波动为零',MISSING_BOUNDARY:'边界缺失',ZERO_DRAWDOWN:'回撤为零'};
    const metrics=node('div',null,'stock-stage-grid');
    for(const [name,label] of [['sharpe','Sharpe'],['calmar','Calmar']]){const metric=evaluation.risk_metrics[name],cell=node('div'),value=node('strong',present(metric.value)?compact(metric.value):'未提供');value.title=saved(metric.value);cell.append(node('span',label,'small'),value,node('p',metric.status==='AVAILABLE'?'原回测范围 · Owner 保存值':labels[metric.status] || metric.status,'small'));metrics.append(cell);}
    const summary=evaluation.execution_summary;
    if(summary)for(const [label,value] of [['双边成交额 / 平均净资产',present(summary.two_sided_turnover)?percent(summary.two_sided_turnover):'未提供 · 平均净资产为零'],['费用 / 初始净资产',percent(summary.fee_ratio)]]){const cell=node('div');cell.append(node('span',label,'small'),node('strong',value));metrics.append(cell);}panel.append(metrics);
    const rf=evaluation.risk_metrics.sharpe.risk_free;panel.append(node('p','无风险利率：'+percent(rf.annual_effective_rate)+'（'+rf.currency+'，年有效利率）；'+(rf.source==='EXPLICIT_ZERO_ASSUMPTION'?'显式零利率实验假设':saved(rf.source))+'。区间缩放不会改变这些指标。','small'));
    const dd=evaluation.drawdown_interval;
    if(dd?.status==='AVAILABLE')panel.append(node('p','最大回撤 '+percent(dd.drawdown)+'：'+dd.peak_session+(dd.peak_is_initial_anchor?'（初始财富锚点，不是保存 NAV 点）':'（保存峰值）')+' → '+dd.trough_session+'（谷值），历时 '+dd.elapsed_calendar_days+' 个自然日；'+(dd.recovery_status==='RECOVERED'?'恢复于 '+dd.recovery_session:'期末尚未恢复')+'。','small'));
    else if(dd?.status==='NO_DRAWDOWN')panel.append(node('p','Owner 报告没有负回撤，不生成峰谷日期。','small'));
    const raw=node('button','查看保存分析及口径原值','text-button');raw.addEventListener('click',()=>openRaw('Owner 保存的账户分析',{risk_metrics:evaluation.risk_metrics,drawdown_interval:dd,execution_summary:summary,spec:evaluation.spec,base_evaluation_ref:evaluation.base_evaluation_ref,benchmark_refs:evaluation.benchmark_refs}));panel.append(raw);
    $('analysis-chart').hidden=false;
    const points=evaluation.analysis_series || [],concentration=new Map((evaluation.concentration_series || []).map(p=>[p.session,p])),ss=points.map(p=>p.session);
    if(!ss.length)return;
    const base=axes(ss,'20 日指标（%）','单证券权重（%）');base.yAxis.forEach(axis=>axis.axisLabel.formatter=value=>percent(String(value)));
    chart('analysis-chart',{...base,animation:false,legend:{top:5,data:['20 日收益','20 日波动（未年化）','最大单证券权重'],textStyle:{fontSize:11,color:'#52677c'}},tooltip:{trigger:'axis',confine:true,formatter:items=>{const day=items[0]?.axisValue,p=points.find(p=>p.session===day),weight=concentration.get(day);return p?tooltipRows(day,[['累计收益',percent(p.account_cumulative_return)],['20 日收益',percent(p.rolling_return_20)],['20 日波动（未年化）',percent(p.rolling_volatility_20)],['最大单证券权重',percent(weight?.maximum_single_security_weight)],['窗口状态',p.rolling_status==='AVAILABLE'?'完整':p.rolling_status==='INSUFFICIENT_WINDOW'?'不足 20 个保存日':'观测缺失']]):'';}},series:[{type:'line',name:'20 日收益',showSymbol:false,data:points.map(p=>number(p.rolling_return_20)),lineStyle:{color:'#547d9e'},connectNulls:false},{type:'line',name:'20 日波动（未年化）',showSymbol:false,data:points.map(p=>number(p.rolling_volatility_20)),lineStyle:{color:'#aa884c',type:'dashed'},connectNulls:false},{type:'line',name:'最大单证券权重',xAxisIndex:1,yAxisIndex:1,showSymbol:false,data:ss.map(s=>number(concentration.get(s)?.maximum_single_security_weight)),lineStyle:{color:'#578471'},connectNulls:false}]},ss,lockDay);
  }
  function bind(){
    $('sidebar-toggle').addEventListener('click',()=>{const closed=document.querySelector('.shell').classList.toggle('navigation-collapsed');$('sidebar-toggle').setAttribute('aria-expanded',String(!closed));$('sidebar-toggle').textContent=closed?'展开 idea':'收起 idea';resize();});
    $('grid-toggle').addEventListener('change',e=>{state.grid=e.target.checked;performance(current());trade(current());});
    $('benchmark-select').addEventListener('change',e=>{state.benchmarkKey=e.target.value;performance(current());});
    $('price-basis-select').addEventListener('change',e=>{state.priceBasisByRun ||= {};state.priceBasisByRun[current().run.run_id]=e.target.value;trade(current());});
    $('saved-analysis').addEventListener('toggle',()=>{if($('saved-analysis').open)analysis(current());});
    $('locate-drawdown').addEventListener('click',()=>{const v=current(),dd=v.evaluation?.drawdown_interval;if(dd?.status!=='AVAILABLE')return;const first=v.run.nav?.[0]?.session;setWindow(dd.peak_session<first?first:dd.peak_session,dd.recovery_session || v.run.nav.at(-1).session);lockDay(dd.trough_session);performance(v);});
    $('unlock-point').addEventListener('click',()=>{state.session='';state.fillId='';state.eventId='';selection(current());renderHeader(current());trade(current());performance(current());});
    for(const prefix of ['', 'performance-']){
      $(prefix+'trade-window').addEventListener('change',e=>{state.tradeWindow={mode:e.target.value,start:$(prefix+'window-start').value,end:$(prefix+'window-end').value};const ss=[...indexed(current()).nav.keys()],w=windowFor(ss);state.interval=e.target.value==='all'?null:w;performance(current());trade(current());renderHeader(current());});
      for(const id of ['window-start','window-end'])$(prefix+id).addEventListener('change',()=>setWindow($(prefix+'window-start').value,$(prefix+'window-end').value));
    }
    let searchTimeout;$('chain-search').addEventListener('input',()=>{clearTimeout(searchTimeout);searchTimeout=setTimeout(()=>renderChain(current()),120);});
    $('chain-security').addEventListener('change',e=>{state.chainSecurity=e.target.value;if(e.target.value){state.security=e.target.value;state.fillId='';state.eventId='';trade(current());}else renderChain(current());});$('chain-status').addEventListener('change',()=>renderChain(current()));
    $('raw-close').addEventListener('click',()=>$('raw-dialog').close());$('raw-source').addEventListener('click',()=>{const v=current();openRaw('所选运行与来源保存引用',{run_id:v.run.run_id,content_digest:v.run.content_digest,committed_sequence:v.run.committed_sequence,evaluation_ref:v.evaluation?.evaluation_ref,signal_ref:v.run.signal_ref,market_ref:v.run.market_ref,profile_ref:v.run.profile_ref,core_version:v.run.core_version,runtime_version:v.run.runtime_version,research:v.research,context:v.market.native_chart?.context || v.market.data_batch?.context,limitations:[...(v.run.limitations || []),...(v.evaluation?.limitations || [])],episode_metrics:v.evaluation?.episode_metrics,spec:v.evaluation?.spec});});
    $('point-step').addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Enter'].includes(e.key))return;e.preventDefault();const ss=[...indexed(current()).nav.keys()],position=Math.max(0,ss.indexOf(state.session)),i=Math.max(0,Math.min(ss.length-1,position+(e.key==='ArrowLeft'?-1:e.key==='ArrowRight'?1:0)));lockDay(ss[i]);});
    window.addEventListener('resize',resize);new ResizeObserver(resize).observe(document.querySelector('main'));
  }
  function resize(){for(const item of instances.values())if(item.getDom().offsetWidth)item.resize();}
  return {performance,trade,summaries,bind,resize,setWindow,renderChain,securityLabel,openRaw,selection,returnPoints,analysis};
};
