const icons={library:'M3 10 12 3l9 7v11h-6v-7H9v7H3Z',watch:'M3 4h18v14H3z M8 22h8 M10 8l5 3-5 3z',moments:'M4 20V5 M4 20h17 M8 15l4-6 4 4 5-8',data:'M5 3h14v18H5z M8 7h8 M8 11h8 M8 15h8',sources:'M12 3l2.8 5.6 6.2.9-4.5 4.4 1.1 6.2L12 17.2 6.4 20l1.1-6.1L3 9.5l6.2-.9Z',history:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l4 2',settings:'M5 12h.01 M12 12h.01 M19 12h.01'};
export function createDrawer({onAction,mascot}){
 const element=document.createElement('nav');element.className='left-drawer glass-shell';element.setAttribute('aria-label','观赛操作');element.inert=true;
 element.innerHTML='<div class="glass-target"></div><div class="glass-content"></div>';const body=element.lastElementChild;
 for(const [action,label] of [['library','选择比赛片段'],['watch','沉浸式观看'],['moments','关键时刻'],['data','球员数据'],['sources','数据来源'],['history','历史成片'],['settings','观看设置']]){const b=document.createElement('button');b.title=label;b.setAttribute('aria-label',label);b.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${icons[action]}"/></svg>`;b.onclick=()=>onAction(action);body.append(b);}
 const m=document.createElement('button');m.className='dock-mascot';m.title='开启或关闭解释图层';m.setAttribute('aria-label',m.title);m.innerHTML=mascot;m.onclick=()=>onAction('annotations');body.append(m);
 return {element,setOpen(v){element.classList.toggle('open',v);element.inert=!v;},get isOpen(){return element.classList.contains('open')}};
}
