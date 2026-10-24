import { theme } from './theme.js';
// One palette shared by the 2D map, 3D robots, route lines and status cards.
const palette=theme.robots;
export const robotColor=id=>id<=palette.length?palette[id-1]:`hsl(${Math.round((id-1)*137.508)%360},64%,69%)`;
