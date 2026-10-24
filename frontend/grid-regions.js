/** Exact visual unions of four-neighbour cells; never bridge gaps or fill holes. */
const key=([x,y])=>`${x},${y}`;

export function filledRectangles(points) {
  const rows=new Map();
  for(const [x,y] of points) {if(!rows.has(y)) rows.set(y,new Set());rows.get(y).add(x);}
  const result=[];let active=new Map(),previous=-2;
  for(const y of [...rows.keys()].sort((a,b)=>a-b)) {
    const xs=[...rows.get(y)].sort((a,b)=>a-b),runs=[];
    for(let i=0;i<xs.length;) {const x=xs[i++];let width=1;while(i<xs.length && xs[i]===x+width) {i++;width++;}runs.push([x,width]);}
    if(y!==previous+1) active.clear();
    const next=new Map();
    for(const [x,width] of runs) {
      const identity=x+':'+width,rectangle=active.get(identity);
      if(rectangle) rectangle.depth++;else result.push({x,y,width,depth:1});
      next.set(identity,rectangle || result.at(-1));
    }
    active=next;previous=y;
  }
  return result;
}

export function connectedRegions(points) {
  const remaining=new Map(points.map(p=>[key(p),p]));
  const regions=[];
  const ordered=[...remaining.values()].sort((a,b)=>a[1]-b[1] || a[0]-b[0]);
  for(const origin of ordered) {
    if(!remaining.delete(key(origin)))continue;
    const cells=[origin];
    for(let i=0;i<cells.length;i++) {
      const [x,y]=cells[i];
      for(const p of [[x-1,y],[x+1,y],[x,y-1],[x,y+1]]) {
        if(remaining.delete(key(p)))cells.push(p);
      }
    }
    const occupied=new Set(cells.map(key)),boundary=[];
    let cx=0,cy=0;
    for(const [x,y] of cells) {
      cx+=x+.5;cy+=y+.5;
      if(!occupied.has(`${x},${y-1}`))boundary.push([x,y,x+1,y]);
      if(!occupied.has(`${x+1},${y}`))boundary.push([x+1,y,x+1,y+1]);
      if(!occupied.has(`${x},${y+1}`))boundary.push([x+1,y+1,x,y+1]);
      if(!occupied.has(`${x-1},${y}`))boundary.push([x,y+1,x,y]);
    }
    cx/=cells.length;cy/=cells.length;
    let label=[cx,cy];
    if(!occupied.has(`${Math.floor(cx)},${Math.floor(cy)}`)) {
      const nearest=cells.reduce((best,p)=>(p[0]+.5-cx)**2+(p[1]+.5-cy)**2 <
        (best[0]+.5-cx)**2+(best[1]+.5-cy)**2?p:best);
      label=[nearest[0]+.5,nearest[1]+.5];
    }
    regions.push({cells,rectangles:filledRectangles(cells),boundary,label});
  }
  return regions;
}
// Physical footprint includes walls/racks; only explicit outside cells are absent.
// Merge grid runs on each axis without bridging a courtyard or a concave cutout.
export function footprintGeometry(width,height,voids=[]) {
  const outside=new Set(voids.map(([x,y])=>`${x},${y}`));
  const inside=(x,y)=>x>=0&&y>=0&&x<width&&y<height&&!outside.has(`${x},${y}`);
  const cells=[],grid=[];
  for(let y=0;y<height;y++)for(let x=0;x<width;x++)if(inside(x,y))cells.push([x,y]);
  function runs(limit,active,emit) {
    let start=-1;
    for(let i=0;i<=limit;i++) {
      if(i<limit&&active(i)) {if(start<0)start=i;}
      else if(start>=0) {emit(start,i);start=-1;}
    }
  }
  for(let x=0;x<=width;x++)runs(height,y=>inside(x-1,y)||inside(x,y),(a,b)=>grid.push([x,a,x,b]));
  for(let y=0;y<=height;y++)runs(width,x=>inside(x,y-1)||inside(x,y),(a,b)=>grid.push([a,y,b,y]));
  return {rectangles:filledRectangles(cells),grid,cellCount:cells.length};
}

