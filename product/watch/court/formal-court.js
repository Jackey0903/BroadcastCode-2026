/** Source-bound formal tactical snapshots; never interpolate or invent tracks. */
export function validateFormalCourt(data, story) {
  if(data?.schema!=='gamebuddy-formal-court-v1'||data.sourceSha256!==story?.sourceVideoSha256||!Array.isArray(data.snapshots)||data.snapshots.length!==3)throw new Error('正式站位来源不匹配');
  let previous=-1;
  for(const snapshot of data.snapshots){
    if(!Number.isFinite(snapshot.t)||snapshot.t<=previous||snapshot.t>story.durationSeconds||!Array.isArray(snapshot.players))throw new Error('正式站位时间无效');
    const ids=new Set();
    for(const p of snapshot.players){if(ids.has(p.id)||!['dark','white'].includes(p.team)||![p.x,p.y].every(Number.isFinite)||p.x<0||p.x>47||p.y<0||p.y>50)throw new Error('正式示意坐标无效');ids.add(p.id);}
    previous=snapshot.t;
  }
  return data;
}
export function sampleFormalCourt(data,time){
  const positions=new Map();let sourceTime=null;
  for(const snapshot of data.snapshots){if(snapshot.t>time+.002)break;sourceTime=snapshot.t;for(const p of snapshot.players)positions.set(p.id,{...p,sourceTime:snapshot.t});}
  return [...positions.values()].map(p=>({...p,status:'estimated',held:Math.abs(time-p.sourceTime)>.08,identityStatus:'anonymous',image:null,reviewed:false}));
}
