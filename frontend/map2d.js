import { robotColor } from './robot-colors.js';
import { theme } from './theme.js';
import { connectedRegions } from './grid-regions.js';
const art = theme.map;
const key = p => `${p[0]},${p[1]}`;

export class Map2D {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.map = null;
    this.zoom = 1;
    this.focusX = this.focusY = 0;
    this.drag = null;
    this.cache = document.createElement('canvas');
    canvas.addEventListener('wheel', e => this.wheel(e), { passive: false });
    canvas.addEventListener('pointerdown', e => this.beginPan(e));
    canvas.addEventListener('pointermove', e => this.pan(e));
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      canvas.addEventListener(event, e => this.endPan(e));
    }
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
    this.resize();
  }
  resize() {
    const r = this.canvas.parentElement.getBoundingClientRect();
    this.width = Math.max(1, r.width); this.height = Math.max(1, r.height);
    this.dpr = Math.min(devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(this.width * this.dpr);
    this.canvas.height = Math.round(this.height * this.dpr);
    this.rebuild();
  }
  setMap(map) { this.map = map; this.parkingRegions=connectedRegions(map.parking); this.recenter(); }
  recenter() {
    if (!this.map) return;
    if (this.drag) this.endPan({ pointerId: this.drag.id });
    this.zoom = 1;
    this.focusX = this.map.width / 2;
    this.focusY = this.map.height / 2;
    this.rebuild();
  }
  local(e) {
    const r = this.canvas.getBoundingClientRect();
    return [(e.clientX-r.left)*this.width/r.width, (e.clientY-r.top)*this.height/r.height];
  }
  limitFocus() {
    // Keep the viewport center on the map, so panning cannot lose it entirely.
    this.focusX = Math.max(0, Math.min(this.map.width, this.focusX));
    this.focusY = Math.max(0, Math.min(this.map.height, this.focusY));
  }
  wheel(e) {
    if (!this.map) return;
    e.preventDefault();
    const pixels = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? this.height : 1);
    const zoom = Math.max(1, Math.min(12, this.zoom*Math.exp(-Math.max(-240, Math.min(240, pixels))*.002)));
    if (zoom === this.zoom) return;
    const [x,y] = this.local(e);
    const worldX = (x-this.ox)/this.cell, worldY = (y-this.oy)/this.cell;
    const cell = this.cell*zoom/this.zoom;
    this.zoom = zoom;
    this.focusX = worldX-(x-this.width/2)/cell;
    this.focusY = worldY-(y-this.height/2)/cell;
    this.limitFocus();this.rebuild();
  }
  beginPan(e) {
    if (!this.map || this.drag || e.button !== 0) return;
    e.preventDefault();
    const [x,y] = this.local(e);
    this.drag = { id: e.pointerId, x, y };
    this.canvas.setPointerCapture(e.pointerId);
    this.canvas.classList.add('dragging');
  }
  pan(e) {
    if (!this.drag || this.drag.id !== e.pointerId) return;
    const [x,y] = this.local(e);
    this.focusX -= (x-this.drag.x)/this.cell;
    this.focusY -= (y-this.drag.y)/this.cell;
    this.drag.x = x;this.drag.y = y;
    this.limitFocus();this.rebuild();
  }
  endPan(e) {
    if (!this.drag || this.drag.id !== e.pointerId) return;
    this.drag = null;this.canvas.classList.remove('dragging');
    if (this.canvas.hasPointerCapture(e.pointerId)) this.canvas.releasePointerCapture(e.pointerId);
  }
  rebuild() {
    if (!this.map) return;
    const m = this.map;
    this.cell = Math.max(.01, Math.min((this.width - 12) / m.width, (this.height - 12) / m.height))*this.zoom;
    this.ox = this.width/2-this.focusX*this.cell;
    this.oy = this.height/2-this.focusY*this.cell;
    this.cache.width = this.canvas.width; this.cache.height = this.canvas.height;
    const c = this.cache.getContext('2d'); c.scale(this.dpr, this.dpr);
    c.fillStyle = art.canvas; c.fillRect(0, 0, this.width, this.height);
    const shelves = new Set(m.shelves.map(key)), obstacles = new Set(m.obstacles.map(key));
    const blocked = new Set(m.blocked.map(key));
    const voids = new Set((m.voids || []).map(key));
    // Rebuild only the visible cells; the raster cache always stays viewport-sized.
    const left=Math.max(0,Math.floor(-this.ox/this.cell)), right=Math.min(m.width,Math.ceil((this.width-this.ox)/this.cell));
    const top=Math.max(0,Math.floor(-this.oy/this.cell)), bottom=Math.min(m.height,Math.ceil((this.height-this.oy)/this.cell));
    for (let y = top; y < bottom; y++) for (let x = left; x < right; x++) {
      const k = `${x},${y}`;
      if (voids.has(k)) continue;
      c.fillStyle = shelves.has(k) ? art.rack : obstacles.has(k) ? art.obstacle : blocked.has(k) ? art.wall : art.floor;
      c.fillRect(this.ox + x*this.cell, this.oy + y*this.cell, this.cell, this.cell);
      c.strokeStyle = blocked.has(k) ? art.edge : art.grid; c.lineWidth = .5;
      c.strokeRect(this.ox + x*this.cell, this.oy + y*this.cell, this.cell, this.cell);
      if (obstacles.has(k)) {
        const px = this.ox + x*this.cell, py = this.oy + y*this.cell;
        const inset=this.cell*.12;
        c.strokeStyle = art.crateEdge; c.beginPath(); c.moveTo(px+inset,py+inset); c.lineTo(px+this.cell-inset,py+this.cell-inset); c.stroke();
      }
    }
    // Cover interior grid lines with an exact union; outline only exposed edges.
    for(const region of this.parkingRegions) {
      c.fillStyle=art.parking;c.beginPath();
      for(const r of region.rectangles)c.rect(this.ox+r.x*this.cell,this.oy+r.y*this.cell,r.width*this.cell,r.depth*this.cell);
      c.fill();
      c.strokeStyle=art.parkingEdge;c.lineWidth=Math.max(.6,this.cell*.045);c.beginPath();
      for(const [x1,y1,x2,y2] of region.boundary) {
        c.moveTo(this.ox+x1*this.cell,this.oy+y1*this.cell);c.lineTo(this.ox+x2*this.cell,this.oy+y2*this.cell);
      }
      c.stroke();c.fillStyle=art.label;c.font=`${Math.max(8,this.cell*.59)}px Microsoft YaHei,sans-serif`;
      c.textAlign='center';c.textBaseline='middle';
      c.fillText('P',this.ox+region.label[0]*this.cell,this.oy+region.label[1]*this.cell);
    }
    for (const [points, color, label] of [[m.pickups,art.pickup,i=>String(i+1)], [m.deliveries,art.delivery,i=>`D${i+1}`]]) {
      points.forEach((p,i) => {
        const [x,y] = this.center(p);
        c.fillStyle = color; c.fillRect(x-this.cell*.4,y-this.cell*.4,this.cell*.8,this.cell*.8);
        c.fillStyle = art.label; c.font = `${Math.max(8,this.cell*.59)}px Microsoft YaHei, sans-serif`;
        c.textAlign='center'; c.textBaseline='middle'; c.fillText(label(i),x,y);
      });
    }
  }
  center(p) { return [this.ox+(p[0]+.5)*this.cell, this.oy+(p[1]+.5)*this.cell]; }
  inspect() {
    return { zoom: this.zoom, cell: this.cell, origin: [this.ox,this.oy],
             focus: [this.focusX,this.focusY], size: [this.width,this.height], dragging: !!this.drag,
             cacheSize: [this.cache.width,this.cache.height],
             parkingCells:this.map?.parking.length||0,parkingRegions:this.parkingRegions?.length||0,
             voidCells:this.map?.voids?.length||0 };
  }
  draw(state, positions, task) {
    if (!this.map || !state) return;
    const c = this.ctx; c.setTransform(1,0,0,1,0,0); c.drawImage(this.cache,0,0); c.scale(this.dpr,this.dpr);
    c.lineJoin='round'; c.lineCap='round';
    for (const r of state.robots) {
      if (r.path.length < 2) continue;
      c.strokeStyle = robotColor(r.id); c.globalAlpha=.8; c.lineWidth = Math.max(1.4,this.cell*.13); c.beginPath();
      r.path.forEach((p,i) => { const [x,y]=this.center(p); i ? c.lineTo(x,y) : c.moveTo(x,y); }); c.stroke(); c.globalAlpha=1;
    }
    if (task) {
      for (const [p,color] of [[task.pickup,art.pickupHighlight],[task.delivery,art.deliveryHighlight]]) {
        const [x,y]=this.center(p); c.strokeStyle=color; c.lineWidth=2;
        c.beginPath(); c.arc(x,y,this.cell*.53,0,Math.PI*2); c.stroke();
      }
    }
    for (const r of state.robots) {
      const [x,y]=this.center(positions[r.id]); const radius=Math.max(4,this.cell*.4);
      c.fillStyle=art.robotShadow; c.beginPath(); c.arc(x+.8,y+1,radius+.6,0,Math.PI*2); c.fill();
      c.fillStyle=robotColor(r.id); c.beginPath(); c.arc(x,y,radius,0,Math.PI*2); c.fill();
      c.fillStyle=art.robotInk; c.font=`bold ${Math.max(8,this.cell*.57)}px sans-serif`; c.textAlign='center'; c.textBaseline='middle'; c.fillText(r.id,x,y);
      if (r.loaded) { c.fillStyle=art.cargo; c.fillRect(x+radius*.35,y-radius*1.25,radius*.7,radius*.65); }
      if (r.urgent) { c.strokeStyle=art.urgent; c.lineWidth=1.7; c.beginPath(); c.arc(x,y,radius+2,0,Math.PI*2); c.stroke(); }
    }
    if (task) {
      const [x,y] = this.center(task.pickup); const size=Math.max(10,this.cell*.65);
      c.font=`${size}px Microsoft YaHei,sans-serif`; const width=size+5, height=size+4;
      c.fillStyle=art.labelBg; c.fillRect(x-width/2,y-this.cell*.6-height,width,height);
      c.strokeStyle=art.pickupHighlight; c.lineWidth=1; c.strokeRect(x-width/2,y-this.cell*.6-height,width,height);
      c.fillStyle=art.pickupHighlight; c.textAlign='center'; c.textBaseline='middle'; c.fillText('取',x,y-this.cell*.6-height/2);
      const [dx,dy]=this.center(task.delivery);
      c.fillStyle=art.deliveryHighlight; c.fillText('送',dx,dy-this.cell*.95);
    }
    this.canvas.dataset.tick = state.tick;
  }
}
