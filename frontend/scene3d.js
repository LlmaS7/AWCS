import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { robotColor } from './robot-colors.js';
import { theme } from './theme.js';
import { filledRectangles as rectangles, connectedRegions, footprintGeometry } from './grid-regions.js';
const art = theme.scene;

function label(text, color=art.labelInk, background=art.labelBg) {
  const canvas=document.createElement('canvas'); canvas.width=160; canvas.height=80;
  const c=canvas.getContext('2d'); c.fillStyle=background;
  c.beginPath(); c.roundRect(4,4,152,72,12); c.fill();
  c.fillStyle=color; c.font='bold 40px Microsoft YaHei,sans-serif'; c.textAlign='center'; c.textBaseline='middle'; c.fillText(text,80,40);
  const texture=new THREE.CanvasTexture(canvas); texture.colorSpace=THREE.SRGBColorSpace;
  const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthTest:false}));
  sprite.scale.set(.85,.425,1); return sprite;
}

function dispose(group) {
  group.traverse(object => {
    object.geometry?.dispose();
    const materials=Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach(m => { m?.map?.dispose(); m?.dispose(); });
  });
  group.clear();
}

export class Scene3D {
  constructor(container) {
    this.container=container; this.robots=new Map(); this.paths=new Map();
    this.highlightKey=null; this.available=false;
    try {
      this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});
      this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1,2));
      this.renderer.setClearColor(art.bg);
      this.renderer.outputColorSpace=THREE.SRGBColorSpace;
      this.renderer.toneMapping=THREE.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure=art.exposure;
      container.prepend(this.renderer.domElement);
      this.scene=new THREE.Scene(); this.scene.fog=new THREE.Fog(art.bg,65,120);
      this.camera=new THREE.PerspectiveCamera(38,1,.1,150);
      this.controls=new OrbitControls(this.camera,this.renderer.domElement);
      this.controls.enableDamping=true; this.controls.dampingFactor=.08;
      this.controls.minDistance=12; this.controls.maxDistance=90;
      this.controls.maxPolarAngle=Math.PI*.48;
      this.scene.add(new THREE.HemisphereLight(art.light,art.ground,art.skyPower));
      const sun=new THREE.DirectionalLight(art.sun,art.sunPower); sun.position.set(8,30,10); this.scene.add(sun);
      this.warehouse=new THREE.Group(); this.scene.add(this.warehouse);
      this.highlights=new THREE.Group(); this.scene.add(this.highlights);
      this.available=true;
      this.renderer.domElement.addEventListener('webglcontextlost',e => { e.preventDefault(); this.available=false; this.error('3D 渲染连接中断，2D 与任务操作仍可使用。'); });
      new ResizeObserver(() => this.resize()).observe(container);
      this.resize();
    } catch (error) { this.error('当前环境未能启动 WebGL 2。2D 预览与任务操作仍可使用。'); console.error(error); }
  }
  error(message) { const e=document.getElementById('scene-error'); e.hidden=false; e.textContent=message; }
  resize() {
    if (!this.renderer) return;
    const r=this.container.getBoundingClientRect();
    this.renderer.setSize(Math.max(1,r.width),Math.max(1,r.height),false);
    this.camera.aspect=r.width/Math.max(1,r.height); this.camera.updateProjectionMatrix();
  }
  recenter() {
    if (!this.map || !this.available) return;
    const {width,height}=this.map;
    const damping=this.controls.enableDamping;
    this.controls.enableDamping=false; this.controls.update(); this.controls.enableDamping=damping;
    this.controls.target.set(width/2,0,height/2);
    const radius=Math.hypot(width,height)/2;
    let distance=radius*1.1;
    this.controls.minDistance=Math.max(4,Math.min(width,height)*.3);
    const direction=new THREE.Vector3(.8,1,1.2).normalize();
    this.camera.far=radius*100;this.camera.updateProjectionMatrix();
    // Fit the actual rectangular footprint, rather than its larger bounding sphere.
    for(let attempt=0;attempt<50;attempt++) {
      this.camera.position.copy(this.controls.target).addScaledVector(direction,distance);
      this.camera.lookAt(this.controls.target);this.camera.updateMatrixWorld();
      const corners=[[0,0],[width,0],[0,height],[width,height]].map(([x,z])=>new THREE.Vector3(x,1.8,z).project(this.camera));
      if(corners.every(p=>Math.abs(p.x)<.91 && Math.abs(p.y)<.86 && p.z>-1 && p.z<1)) break;
      distance*=1.08;
    }
    this.controls.maxDistance=distance*3;
    this.camera.far=distance*5;this.camera.updateProjectionMatrix();
    this.scene.fog.near=distance*2;this.scene.fog.far=distance*4;
    this.controls.update();
  }
  boxes(rects, height, elevation, color, inset=0) {
    if(!rects.length) return;
    const mesh=new THREE.InstancedMesh(new THREE.BoxGeometry(1,1,1),new THREE.MeshStandardMaterial({color,roughness:art.roughness,metalness:art.metalness}),rects.length);
    const transform=new THREE.Object3D();
    rects.forEach((r,i)=>{
      transform.position.set(r.x+r.width/2,elevation,r.y+r.depth/2);
      transform.scale.set(r.width-inset,height,r.depth-inset);transform.updateMatrix();mesh.setMatrixAt(i,transform.matrix);
    });
    mesh.computeBoundingSphere();this.warehouse.add(mesh);
  }
  box(width,height,depth,color,x,y,z,group=this.warehouse) {
    const mesh=new THREE.Mesh(new THREE.BoxGeometry(width,height,depth),
      new THREE.MeshStandardMaterial({color,roughness:art.roughness,metalness:art.metalness}));
    mesh.position.set(x,y,z); group.add(mesh); return mesh;
  }
  setMap(map) {
    this.map=map;
    this.parkingRegions=connectedRegions(map.parking);
    if (!this.available) return;
    dispose(this.warehouse); dispose(this.highlights); this.highlightKey=null;
    for (const path of this.paths.values()) { this.scene.remove(path); path.geometry.dispose(); path.material.dispose(); }
    this.paths.clear();
    for(const robot of this.robots.values()) {this.scene.remove(robot.group);dispose(robot.group);}
    this.robots.clear();
    const {width,height}=map;
    const coords=[];
    this.footprint=footprintGeometry(width,height,map.voids||[]);
    if(map.voids?.length) {
      this.boxes(this.footprint.rectangles,.18,-.13,art.base);
      this.boxes(this.footprint.rectangles,.01,-.005,art.floor);
      for(const [x1,z1,x2,z2] of this.footprint.grid)coords.push(x1,.012,z1,x2,.012,z2);
    } else {
      const floor=new THREE.Mesh(new THREE.PlaneGeometry(width,height),new THREE.MeshStandardMaterial({color:art.floor,roughness:1}));
      floor.rotation.x=-Math.PI/2; floor.position.set(width/2,0,height/2); this.warehouse.add(floor);
      this.box(width+.35,.18,height+.35,art.base,width/2,-.13,height/2);
      for(let x=0;x<=width;x++) coords.push(x,.012,0,x,.012,height);
      for(let z=0;z<=height;z++) coords.push(0,.012,z,width,.012,z);
    }
    const grid=new THREE.BufferGeometry(); grid.setAttribute('position',new THREE.Float32BufferAttribute(coords,3));
    this.warehouse.add(new THREE.LineSegments(grid,new THREE.LineBasicMaterial({color:art.grid,transparent:true,opacity:.32})));
    this.boxes(rectangles(map.walls),.38,.19,art.wall);
    const racks=rectangles(map.shelves);
    this.boxes(racks,1.55,.775,art.rack,.14);
    for(const y of [.38,.85,1.35]) this.boxes(racks,.055,y,art.rail,.08);
    this.boxes(racks,.16,1.63,art.cap,.22);
    this.boxes(map.obstacles.map(([x,y])=>({x,y,width:1,depth:1})),.62,.31,art.crate,.2);
    const parkingRects=this.parkingRegions.flatMap(r=>r.rectangles),edges=[];
    this.boxes(parkingRects,.025,.025,art.parking);
    for(const region of this.parkingRegions) {
      for(const [x1,z1,x2,z2] of region.boundary)edges.push(x1,.043,z1,x2,.043,z2);
      const s=label('P');s.position.set(region.label[0],.55,region.label[1]);this.warehouse.add(s);
    }
    if(edges.length) {
      const outline=new THREE.BufferGeometry();outline.setAttribute('position',new THREE.Float32BufferAttribute(edges,3));
      this.warehouse.add(new THREE.LineSegments(outline,new THREE.LineBasicMaterial({color:art.parkingEdge})));
    }
    for(const [points,color,prefix] of [[map.pickups,art.pickup,''],[map.deliveries,art.delivery,'D']]) {
      points.forEach(([x,z],index)=>{
        this.box(.85,.025,.85,color,x+.5,.025,z+.5);
        const s=label(prefix+(index+1));
        s.position.set(x+.5,.55,z+.5); this.warehouse.add(s);
      });
    }
    this.recenter();
  }
  robot(id) {
    if(this.robots.has(id)) return this.robots.get(id);
    const g=new THREE.Group(), color=robotColor(id);
    this.box(.7,.26,.88,color,0,.29,0,g);
    this.box(.52,.13,.62,art.body,0,.48,0,g);
    for(const x of [-.36,.36]) for(const z of [-.28,.28]) this.box(.13,.18,.24,art.wheels,x,.16,z,g);
    const cargo=this.box(.34,.3,.34,art.cargo,0,.69,0,g); cargo.visible=false;
    const number=label('R'+id); number.position.set(0,1.08,0); number.scale.set(.72,.36,1); g.add(number);
    const ring=new THREE.Mesh(new THREE.RingGeometry(.5,.58,32),new THREE.MeshBasicMaterial({color:art.urgent,side:THREE.DoubleSide}));
    ring.rotation.x=-Math.PI/2; ring.position.y=.04; ring.visible=false; g.add(ring);
    const result={group:g,cargo,ring}; this.robots.set(id,result); this.scene.add(g); return result;
  }
  update(state, task) {
    if(!this.available) return;
    for(const r of state.robots) {
      const robot=this.robot(r.id); robot.cargo.visible=r.loaded; robot.ring.visible=r.urgent;
      let line=this.paths.get(r.id);
      if(r.path.length>1) {
        if(!line) {
          line=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:robotColor(r.id),transparent:true,opacity:.85}));
          line.frustumCulled=false;this.scene.add(line);this.paths.set(r.id,line);
        }
        let attribute=line.geometry.getAttribute('position');
        if(!attribute || attribute.count<r.path.length) {
          attribute=new THREE.Float32BufferAttribute(new Float32Array(3*2**Math.ceil(Math.log2(r.path.length))),3);
          line.geometry.setAttribute('position',attribute);
        }
        r.path.forEach(([x,z],i)=>attribute.setXYZ(i,x+.5,.075,z+.5));
        attribute.needsUpdate=true;line.geometry.setDrawRange(0,r.path.length);line.visible=true;
      } else if(line) line.visible=false;
    }
    this.highlight(task);
  }
  highlight(task) {
    if(!this.available) return;
    const key=task ? task.id+':'+task.pickup.join(',')+':'+task.delivery.join(',') : null;
    if(key===this.highlightKey) return;
    dispose(this.highlights); this.highlightKey=key;
    if(task) for(const [p,color,word] of [[task.pickup,0x198abd,'取'],[task.delivery,0x21996e,'送']]) {
      const ring=new THREE.Mesh(new THREE.RingGeometry(.6,.69,40),new THREE.MeshBasicMaterial({color,side:THREE.DoubleSide}));
      ring.rotation.x=-Math.PI/2; ring.position.set(p[0]+.5,.06,p[1]+.5); this.highlights.add(ring);
      const s=label(word); s.position.set(p[0]+.5,1.22,p[1]+.5); s.scale.set(.65,.325,1); this.highlights.add(s);
    }
  }
  draw(state, positions) {
    if(!this.available || !state) return;
    for(const r of state.robots) {
      const p=positions[r.id], robot=this.robot(r.id); robot.group.position.set(p[0]+.5,0,p[1]+.5);
      const dx=r.position[0]-r.previous[0], dz=r.position[1]-r.previous[1];
      if(dx || dz) robot.group.rotation.y=Math.atan2(dx,dz);
    }
    this.controls.update(); this.renderer.render(this.scene,this.camera);
    this.container.dataset.tick=state.tick;
  }
  inspect() {
    return {webgl2:this.available && typeof WebGL2RenderingContext!=='undefined' && this.renderer.getContext() instanceof WebGL2RenderingContext,
            robotCount:this.robots.size, drawCalls:this.renderer?.info.render.calls ?? 0,
            parkingRegionCount:this.parkingRegions?.length||0,parkingCellCount:this.map?.parking.length||0,
            floorCellCount:this.footprint?.cellCount||0,voidCellCount:this.map?.voids?.length||0,
            positions:[...this.robots.entries()].map(([id,r])=>({id,x:r.group.position.x-.5,y:r.group.position.z-.5}))};
  }
}
