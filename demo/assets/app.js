const D = DEMO_DATA;
const canvas = document.getElementById('map');
const ctx = canvas.getContext('2d');
const W = canvas.width, H = canvas.height;

function project(lat, lon){
  const x = (lon + 180) / 360 * W;
  const y = (90 - lat) / 180 * H;
  return [x, y];
}

let currentStrategy = 'cgr';
let currentT = D.disruption_window[0];
let playing = false;
let playTimer = null;

const slider = document.getElementById('timeSlider');
slider.max = D.horizon - 1;

function traceFor(strat){ return strat === 'cgr' ? D.cgr_trace : D.hybrid_trace; }

// Build a lookup: for each integer t, what is the "state" of the message (node or hop-in-progress)
function buildStateTimeline(trace){
  const timeline = {};
  let lastNode = D.source;
  let lastMode = 'cgr';
  for(const ev of trace){
    if(ev.status === 'hop'){
      timeline[ev.t] = {node: ev.to, mode: ev.mode, status:'hop', from: ev.from};
      lastNode = ev.to; lastMode = ev.mode;
    } else if(ev.status === 'flood'){
      timeline[ev.t] = {node: ev.node, mode:'epidemic', status:'flood', neighbors: ev.neighbors, reliability: ev.reliability};
      lastNode = ev.node; lastMode = 'epidemic';
    } else if(ev.status === 'blocked'){
      timeline[ev.t] = {node: ev.node, mode:lastMode, status:'blocked', attempted: ev.attempted, reliability: ev.reliability};
    } else if(ev.status === 'delivered' || ev.status === 'failed' || ev.status === 'stalled'){
      timeline[ev.t] = {node: ev.node, mode:lastMode, status: ev.status};
    }
  }
  return timeline;
}

const timelines = { cgr: buildStateTimeline(D.cgr_trace), hybrid: buildStateTimeline(D.hybrid_trace) };

function currentMessageState(strat, t){
  const tl = timelines[strat];
  const trace = traceFor(strat);
  const tMin = trace[0].t, tMax = trace[trace.length-1].t;
  if(t < tMin) return {node: D.source, mode:'cgr', status:'pending'};
  if(t > tMax) return {node: D.dest, mode:'delivered', status: trace[trace.length-1].status};
  // find closest known state at or before t
  for(let tt = Math.min(t, tMax); tt >= tMin; tt--){
    if(tl[tt]) return tl[tt];
  }
  return {node: D.source, mode:'cgr', status:'pending'};
}

function drawMap(t){
  ctx.clearRect(0,0,W,H);
  // grid
  ctx.strokeStyle = 'rgba(255,255,255,0.045)';
  ctx.lineWidth = 1;
  for(let i=0;i<=12;i++){ const x=i/12*W; ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
  for(let i=0;i<=6;i++){ const y=i/6*H; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }

  const frame = D.frames[t];
  const edges = D.edge_frames[t];
  const inDisruption = t >= D.disruption_window[0] && t < D.disruption_window[1];

  // edges
  ctx.lineWidth = 1;
  for(const [u,v,kind] of edges){
    const pu = u.startsWith('GCS') ? D.ground_points[u] : frame[u];
    const pv = v.startsWith('GCS') ? D.ground_points[v] : frame[v];
    if(!pu || !pv) continue;
    const [x1,y1] = project(pu[0], pu[1]);
    const [x2,y2] = project(pv[0], pv[1]);
    if(Math.abs(x1-x2) > W*0.6) continue; // skip antimeridian-wrapping lines for clarity
    ctx.strokeStyle = kind === 'ISL' ? 'rgba(79,114,176,0.35)' : 'rgba(255,180,84,0.3)';
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
  }

  // ground stations
  for(const g of D.ground_names){
    const [x,y] = project(D.ground_points[g][0], D.ground_points[g][1]);
    ctx.fillStyle = '#ffb454';
    ctx.beginPath(); ctx.moveTo(x,y-6); ctx.lineTo(x-5,y+4); ctx.lineTo(x+5,y+4); ctx.closePath(); ctx.fill();
  }

  // satellites
  for(const name of D.sat_names){
    const p = frame[name];
    if(!p) continue;
    const [x,y] = project(p[0], p[1]);
    ctx.fillStyle = '#4C72B0';
    ctx.beginPath(); ctx.arc(x,y,3,0,7); ctx.fill();
  }

  // message marker
  const state = currentMessageState(currentStrategy, t);
  const nodePos = state.node.startsWith('GCS') ? D.ground_points[state.node] : frame[state.node];
  if(nodePos){
    const [x,y] = project(nodePos[0], nodePos[1]);
    const color = state.mode === 'epidemic' ? '#ffb454' : '#4fd1ff';
    ctx.fillStyle = color;
    ctx.shadowColor = color; ctx.shadowBlur = 14;
    ctx.beginPath(); ctx.arc(x,y,7,0,7); ctx.fill();
    ctx.shadowBlur = 0;
    // pulse ring
    ctx.strokeStyle = color; ctx.globalAlpha = 0.5; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x,y,11,0,7); ctx.stroke();
    ctx.globalAlpha = 1;

    // if flooding, draw faint lines to neighbors being flooded
    if(state.status === 'flood' && state.neighbors){
      for(const nb of state.neighbors){
        const np = nb.startsWith('GCS') ? D.ground_points[nb] : frame[nb];
        if(!np) continue;
        const [x2,y2] = project(np[0], np[1]);
        ctx.strokeStyle = 'rgba(255,180,84,0.7)'; ctx.lineWidth = 1.5;
        ctx.setLineDash([3,3]);
        ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(x2,y2); ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }

  document.getElementById('mapWrap').classList.toggle('disrupted', inDisruption);
  document.getElementById('disruptionBadge').classList.toggle('active', inDisruption);
}

function secToClock(s){
  const m = Math.floor(s/60), sec = Math.round(s%60);
  return `${m}:${sec.toString().padStart(2,'0')}`;
}

function updateTelemetry(t){
  const state = currentMessageState(currentStrategy, t);
  const modeEl = document.getElementById('teleMode');
  const nodeEl = document.getElementById('teleNode');
  const statusEl = document.getElementById('teleStatus');
  const relRow = document.getElementById('relRow');

  if(state.mode === 'epidemic'){
    modeEl.innerHTML = '<span class="badge epidemic">EPIDEMIC FLOOD</span>';
  } else if(state.status === 'delivered'){
    modeEl.innerHTML = '<span class="badge good">DELIVERED</span>';
  } else {
    modeEl.innerHTML = '<span class="badge cgr">CGR-LITE</span>';
  }
  nodeEl.textContent = state.node;
  statusEl.textContent = {
    pending: 'awaiting injection', hop:'in transit', flood:'broadcasting copies',
    blocked:'link unavailable, replanning', delivered:'delivered to destination',
    failed:'delivery failed', stalled:'no path available'
  }[state.status] || state.status;

  if(currentStrategy === 'hybrid'){
    relRow.style.display = 'flex';
    const r = state.reliability;
    if(r !== undefined){
      document.getElementById('teleReliability').textContent = r.toFixed(2);
      document.getElementById('relFill').style.width = (r*100) + '%';
    }
  } else {
    relRow.style.display = 'none';
  }

  document.getElementById('timeLabel').textContent = `t=${t} (${secToClock(t*D.step_seconds)})`;
}

function rebuildLog(t){
  const trace = traceFor(currentStrategy);
  const log = document.getElementById('log');
  log.innerHTML = '';
  for(const ev of trace){
    if(ev.t > t) break;
    const div = document.createElement('div');
    let cls = ev.status, text = '';
    if(ev.status === 'hop') text = `t=${ev.t}  ${ev.from} → ${ev.to}  [${ev.mode}]`;
    else if(ev.status === 'flood') text = `t=${ev.t}  ${ev.node} broadcasting (R=${ev.reliability})`;
    else if(ev.status === 'blocked') text = `t=${ev.t}  ${ev.node} link to ${ev.attempted} unavailable`;
    else if(ev.status === 'delivered') text = `t=${ev.t}  ✓ DELIVERED at ${ev.node}`;
    else text = `t=${ev.t}  ${ev.status}`;
    div.className = cls; div.textContent = text;
    log.appendChild(div);
  }
}

function render(){
  drawMap(currentT);
  updateTelemetry(currentT);
  rebuildLog(currentT);
  slider.value = currentT;
}

document.querySelectorAll('.strategy-toggle button').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('.strategy-toggle button').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    currentStrategy = btn.dataset.strat;
    render();
  });
});

slider.addEventListener('input', ()=>{
  currentT = parseInt(slider.value);
  render();
});

document.getElementById('playBtn').addEventListener('click', ()=>{
  playing = !playing;
  document.getElementById('playBtn').textContent = playing ? '⏸' : '▶';
  if(playing){
    playTimer = setInterval(()=>{
      currentT = (currentT + 1) % D.horizon;
      render();
    }, 220);
  } else {
    clearInterval(playTimer);
  }
});

document.getElementById('jumpStart').addEventListener('click', ()=>{ currentT = 0; render(); });
document.getElementById('jumpDisruption').addEventListener('click', ()=>{ currentT = D.disruption_window[0]; render(); });
document.getElementById('jumpEnd').addEventListener('click', ()=>{
  const trace = traceFor(currentStrategy);
  currentT = trace[trace.length-1].t; render();
});

// ---------------- multi-seed results ----------------
const order = ["Naive","Epidemic","CGR-lite","Hybrid-Adaptive"];
const labelOf = n => n === "Hybrid-Adaptive" ? "Hybrid-Adaptive (ours)" : n;
const fmt = (a, d, k) => (a.mean*k).toFixed(d) + " ± " + (a.std*k).toFixed(d);
const metricsBody = document.getElementById('metricsBody');
for(const n of order){
  const m = MS.baseline[n]; const tr = document.createElement('tr');
  if(n.startsWith('Hybrid')) tr.className = 'ours';
  tr.innerHTML = `<td>${labelOf(n)}</td><td class="num">${fmt(m.delivery_rate,1,100)}%</td><td class="num">${fmt(m.avg_latency_s,0,1)} s</td><td class="num">${fmt(m.transmissions,0,1)}</td><td class="num">${(m.network_utilization.mean*100).toFixed(1)}%</td>`;
  metricsBody.appendChild(tr);
}
(function(){
  const c = document.getElementById('sweepChart'), g = c.getContext('2d'), W = c.width, H = c.height;
  const L = 70, Rm = 46, T = 70, B = 55, pw = W-L-Rm, ph = H-T-B;
  const col = {Naive:'#8A97A8', Epidemic:'#F29E2E', 'CGR-lite':'#4C72B0', 'Hybrid-Adaptive':'#4fd1ff'};
  const X = i => L + i*pw/(MS.levels.length-1), Y = v => T + ph - (v/100)*ph;
  g.font = '14px sans-serif'; g.textAlign = 'right'; g.fillStyle = '#8291ac';
  for(let v = 0; v <= 100; v += 20){ g.strokeStyle = '#1f2c47'; g.lineWidth = 1; g.beginPath(); g.moveTo(L,Y(v)); g.lineTo(W-Rm,Y(v)); g.stroke(); g.fillText(v+'%', L-8, Y(v)+5); }
  g.textAlign = 'center'; MS.levels.forEach((l,i) => g.fillText('+'+Math.round(l*100)+'%', X(i), H-30));
  g.fillText('Extra unpredicted link failures', L+pw/2, H-8);
  g.textAlign = 'left'; g.fillStyle = '#dfe7f5'; g.font = '600 16px sans-serif';
  g.fillText('Delivery vs. disruption — mean ± std over '+MS.n_seeds+' seeds', L, 24);
  g.font = '14px sans-serif';
  order.forEach((n,i) => { const x = L + i*170; g.fillStyle = col[n]; g.fillRect(x, 38, 14, 14); g.fillStyle = '#dfe7f5'; g.fillText(labelOf(n), x+20, 50); });
  order.forEach(n => {
    g.strokeStyle = col[n]; g.fillStyle = col[n]; g.lineWidth = n.startsWith('Hybrid') ? 3.5 : 2.2;
    g.beginPath(); MS.sweep[n].forEach((a,i) => { const x = X(i), y = Y(a.mean*100); i ? g.lineTo(x,y) : g.moveTo(x,y); }); g.stroke();
    MS.sweep[n].forEach((a,i) => { const x = X(i); g.lineWidth = 1.5; g.beginPath(); g.moveTo(x, Y(Math.max(0,a.mean-a.std)*100)); g.lineTo(x, Y(Math.min(1,a.mean+a.std)*100)); g.stroke(); g.beginPath(); g.arc(x, Y(a.mean*100), 4, 0, 7); g.fill(); });
  });
})();

render();
