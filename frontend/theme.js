// Industrial graphite. Keep the 2D map dark and the 3D floor light for depth.
// This module contains visual values only; it never changes simulation state.
export const theme = Object.freeze({
  robots: Object.freeze([
    '#68baff', '#f0b466', '#76d1a3', '#b195f0', '#ef8295', '#f0cd60',
    '#55d6dd', '#f08ab6', '#b6d873', '#9facff', '#7bc9ba', '#e69b7a',
  ]),
  map: Object.freeze({
    canvas: '#161a1e', floor: '#22292e', rack: '#68757b', wall: '#39464d',
    obstacle: '#b39a72', edge: '#46565e', grid: '#354149', crateEdge: '#796341',
    pickup: '#a0c8dc', delivery: '#a4d2b9', parking: '#c0b4d2', parkingEdge: '#7c6f91', label: '#17232b',
    pickupHighlight: '#68baff', deliveryHighlight: '#76d1a3', labelBg: '#1c2b35',
    robotShadow: '#101416', robotInk: '#17232b', cargo: '#f7e5b1', urgent: '#f7a2a6',
  }),
  scene: Object.freeze({
    bg: '#1c2126', floor: '#d7d9d3', grid: '#a5aba6', base: '#434b4d',
    wall: '#545e64', rack: '#697479', rail: '#b4b6ad', cap: '#484f51',
    crate: '#b99a69', pickup: '#89b6ca', delivery: '#85b79b', parking: '#b3a5c4', parkingEdge: '#76678b',
    light: '#e7f0f4', ground: '#62655d', sun: '#fff0d3',
    skyPower: 2.2, sunPower: 2.5, roughness: .82, metalness: .23, exposure: 1.05,
    labelInk: '#263c45', labelBg: '#f0eee4', body: '#434b4d', wheels: '#252b2e',
    cargo: '#f1d59b', urgent: '#f7a2a6',
  }),
});
