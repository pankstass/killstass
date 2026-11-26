import { esc, t } from "./core.js";
/* v1.12 — ready-made killzone terrain («Готовый террейн») for the killzone sketch (web/map.js): Killzone: Volkus
   as laid out on the six Approved Ops 2025 maps, and the variant of map 3 from the example sent by the user
   (volkus3.jpg). Digitised from the map images (contours of the terrain, wall and door lines, letters and markers
   taken off a 1″ grid, then checked against the images by eye); inches from the top-left corner of the 30″ × 22″
   board.
   s1, depth — the edge and the depth of player 1's drop zone (player 2 has the opposite edge); on the official
   maps player 1 is the grey side and player 2 the orange one. fill, dark — terrain and its highest level (SVG
   paths); dashed — pieces standing partly beneath another feature; walls, doors — wall lines and the doors in
   them; labels — the letters of the map key; obj — objective markers [x, y, side], side 0 is the central one.
   The ids are mirrored in api/boards.py (LAYOUTS): tests/test_v112.py keeps both lists in step. */
export const LAYOUTS = [
  {
    id: "volkus-2025-1",
    kz: "volkus",
    n: 1,
    set: "ao2025",
    s1: "left",
    depth: 6,
    fill: "M19 17.58L19 19.99L19.74 19.99L19.74 17.58ZM18.45 13.42L15.21 13.42L15.21 18.99L15.41 18.99L16.03 18.36L15.74 18.11L15.74 17.62L16.36 17.28L16.54 17.11L16.99 17.11L17.17 16.61L17.32 16.61L18 16.99L18.16 16.99L18.45 16.78L18.45 15.88L18.07 15.57L18.07 15.38L18.45 14.66ZM3.21 15.17L3.21 18.78L10.78 18.78L10.78 15.17L8.96 15.17L7.82 16.25L6.83 16.25L6.7 16.16L6.71 16.03L7.03 16.03L7.03 12.96L5.96 12.96L5.95 15.71L5.79 15.71L4.78 15.17ZM9.54 11.29L9.54 13.7L10.7 13.7L10.7 11.29ZM3.29 11.29L3.29 14.7L5.16 14.7L5.16 11.29ZM13 10L13 11.99L16.49 11.99L16.49 10ZM19 8.12L19 10.95L19.99 10.95L19.99 8.12ZM20.46 3.21L20.46 4.24L20.71 4.42L20.71 4.66L20.12 6.21L20.29 6.36L20.45 6.41L20.5 6.57L20.38 6.67L20.21 6.99L19.92 7.33L19.92 7.74L20.46 7.92L20.46 8.11L20.12 9.03L21.28 9.03L21.71 8.66L21.91 8.66L22.58 9.03L23.78 9.03L23.78 3.21ZM15.08 2.29L15.08 4.78L16.7 4.78L16.7 2.29ZM9.21 2.21L9.21 7.78L11.49 7.78L11.49 6.88L12.41 6.07L12.41 4.83L12.92 4.28L12.99 4.28L13.12 4.07L13.25 4.08L13.29 4.62L13.25 5.99L13.99 5.99L13.99 4L13.33 4L13.32 3.88L13.42 3.78L14.07 3.78L14.57 3.32L14.57 2.21Z",
    dark: "M8.75 16.62L8.75 18.78L10.78 18.78L10.78 16.62Z",
    dashed: [[6, 13, 1, 3]],
    walls:
      "M9.04 2.15H17.05M19.62 3.15H24.05M4.71 6.94H6.25M9.04 7.94H17.05M3.04 11.15H11.04M21.12 12.15H24.05M15.04 13.35H18.83M3.04 18.94H11.04M3.15 11.04V19.05M6.15 2.33V7.04M9.15 2.04V8.04M10.94 11.04V19.05M15.15 13.24V19M16.94 2.04V8.04M23.94 3.04V9.54M23.94 12.04V17.58",
    doors: "M21.75 3.15H23.62M6.62 18.94H8.54M9.15 2.58V3.75M15.15 14V15.88",
    labels: [
      ["A", 10.98, 4.75],
      ["B", 7.48, 17.4],
      ["C", 22.25, 5.92],
      ["D", 16.62, 15.08],
      ["E", 23.38, 12.62],
      ["F", 5.58, 6.38],
      ["G", 6.5, 14.5],
      ["H", 19.5, 9.52],
      ["I", 14.73, 11],
      ["J", 19.38, 18.77],
      ["K", 13.62, 5],
      ["L", 4.21, 13],
      ["M", 15.88, 3.54],
      ["N", 10.12, 12.5],
    ],
    obj: [
      [15, 6, 0],
      [11.75, 11.75, 1],
      [18.25, 18.25, 2],
    ],
  },
  {
    id: "volkus-2025-2",
    kz: "volkus",
    n: 2,
    set: "ao2025",
    s1: "left",
    depth: 6,
    fill: "M14.62 19.58L14.62 21.99L15.36 21.99L15.36 19.58ZM23 19.17L23 21.99L23.99 21.99L23.99 19.17ZM6.21 13.96L6.21 19.78L9.53 19.78L9.53 18.75L9.28 18.57L9.28 18.33L9.36 18.24L9.53 17.62L9.86 16.82L9.82 16.71L9.49 16.53L9.49 16.42L9.61 16.32L9.78 16L10.07 15.66L10.07 15.25L9.53 15.07L9.53 14.88L9.86 13.96L8.71 13.96L8.24 14.33L8.08 14.33L7.41 13.96ZM22.08 11.29L22.08 13.78L23.7 13.78L23.7 11.29ZM21.53 11.21L16.21 11.21L16.21 16.78L18.49 16.78L18.49 15.88L19.33 15.07L19.41 15.07L19.41 13.83L20.42 12.78L21.07 12.78L21.42 12.41L21.57 12.32ZM6.21 6.17L6.21 9.78L13.78 9.78L13.78 6.17L11.96 6.17L11.16 6.96L11.04 6.96L11.03 4.96L9.96 4.96L9.95 7.25L9.83 7.25L9.78 7.17L7.78 6.17ZM14.25 4L14.25 5.99L17.74 5.99L17.74 4ZM23.78 3.21L23.58 3.21L22.96 3.83L23.25 4.08L23.25 4.57L22.62 4.92L22.45 5.08L22 5.08L21.82 5.58L21.67 5.58L20.99 5.21L20.83 5.21L20.54 5.42L20.54 6.32L20.92 6.62L20.92 6.82L20.54 7.54L20.54 8.78L23.78 8.78ZM12.54 2.29L12.54 4.7L13.7 4.7L13.7 2.29ZM6.29 2.29L6.29 5.7L8.16 5.7L8.16 2.29ZM16 0L16 1.99L16.74 1.99L16.74 0Z",
    dark: "M11.75 7.62L11.75 9.78L13.78 9.78L13.78 7.62Z",
    dashed: [[10, 5, 1, 3]],
    walls:
      "M6.04 2.15H14.04M18.05 3.48H19.54M20.21 8.94H24.05M6.04 9.94H14.04M16.05 11.15H24.05M10.12 13.6H13.04M16.05 16.94H24.05M6.04 19.94H10.42M6.15 2.04V10.04M6.15 13.5V20.05M12.94 13.49V19.04M13.94 2.04V10.04M16.15 11.04V17.05M18.15 3.38V8.04M23.94 3.21V9.04M23.94 11.04V17.05",
    doors: "M9.62 9.94H11.54M6.38 19.94H8.25M16.15 11.58V12.75M23.94 6.33V8.21",
    labels: [
      ["A", 17.98, 13.75],
      ["B", 10.46, 8.92],
      ["C", 7.75, 17.08],
      ["D", 22.38, 7.12],
      ["E", 12.38, 14.08],
      ["F", 18.62, 3.96],
      ["G", 10.5, 6.5],
      ["H", 23.5, 20.56],
      ["I", 15.98, 5],
      ["J", 15, 20.77],
      ["K", 16.38, 1],
      ["L", 7.21, 4],
      ["M", 22.88, 12.54],
      ["N", 13.12, 3.5],
    ],
    obj: [
      [15, 18.25, 0],
      [11.25, 4.75, 1],
      [18.75, 9.25, 2],
    ],
  },
  {
    id: "volkus-2025-3",
    kz: "volkus",
    n: 3,
    set: "ao2025",
    s1: "left",
    depth: 6,
    fill: "M6.29 17.29L6.29 19.7L7.45 19.7L7.45 17.29ZM11.83 16.29L11.83 19.7L13.7 19.7L13.7 16.29ZM17.21 16.54L17.21 19.78L22.78 19.78L22.78 19.58L22.16 18.96L21.91 19.25L21.42 19.25L21.07 18.62L20.91 18.45L20.91 18L20.41 17.82L20.41 17.67L20.74 17L20.99 16.99L20.99 16.25L19 16.25L18.99 16.75L18.83 16.75L18.45 16.54ZM6.21 12.21L6.21 15.82L8.03 15.82L8.88 14.99L8.99 14.99L9 17.99L10.99 17.99L11 15.24L11.11 15.24L12.21 15.82L13.78 15.82L13.78 12.21ZM18 12L18 14.82L18.99 14.82L18.99 12ZM9 6L9 8.99L9.99 8.99L9.99 6ZM18.21 4.46L18.21 9.78L23.78 9.78L23.78 7.5L22.88 7.5L22.07 6.66L22.07 6.58L20.83 6.58L19.78 5.57L19.78 4.92L19.41 4.57L19.32 4.42ZM11.46 3.71L11.46 4.74L11.71 4.92L11.71 5.16L11.62 5.25L11.46 5.86L11.12 6.67L11.17 6.78L11.5 6.96L11.5 7.07L11.38 7.17L11.21 7.49L10.92 7.83L10.92 8.24L11.46 8.42L11.46 8.61L11.12 9.53L12.28 9.53L12.71 9.16L12.91 9.16L13.58 9.53L14.78 9.53L14.78 3.71ZM18.29 2.29L18.29 3.91L20.78 3.91L20.78 2.29ZM12 0L12 2.41L12.74 2.41L12.74 0Z",
    dark: "M6.21 12.21L6.21 14.36L8.24 14.36L8.24 12.21Z",
    dashed: [
      [9, 14.5, 2, 3.5],
      [19, 16.25, 2, 0.75],
    ],
    walls:
      "M18.05 2.15H24.05M10.62 3.65H15.04M6.04 4.48H7.54M18.05 9.94H24.05M6.04 12.15H14.04M21.12 12.15H24.05M6.04 19.94H14.04M17.05 19.94H22.79M6.15 4.38V9.04M6.15 12.04V20.05M13.94 12.04V20.05M14.94 3.54V10.04M17.15 16.21V20.05M18.15 2.04V10.04M23.94 2.04V10.04M23.94 12.04V17.58",
    doors:
      "M12.75 3.65H14.62M18.58 9.94H19.75M8.46 12.15H10.38M17.79 19.94H19.67",
    labels: [
      ["A", 20.75, 8.02],
      ["B", 9.54, 13.04],
      ["C", 13.25, 6.42],
      ["D", 17.62, 19.38],
      ["E", 23.38, 12.62],
      ["F", 6.62, 4.96],
      ["G", 9.5, 7.5],
      ["H", 18.5, 13.4],
      ["I", 10.02, 16.25],
      ["J", 12.38, 1.19],
      ["K", 20, 16.62],
      ["L", 12.75, 18],
      ["M", 19.54, 3.08],
      ["N", 6.88, 18.5],
    ],
    obj: [
      [15, 11, 0],
      [11.25, 2.75, 1],
      [19, 18.25, 2],
    ],
  },
  {
    id: "volkus-2025-4",
    kz: "volkus",
    n: 4,
    set: "ao2025",
    s1: "bottom",
    depth: 3,
    fill: "M15 18L15 18.99L17.99 18.99L17.99 18ZM4.46 15.12L4.46 16.28L4.83 16.75L4.83 16.91L4.46 17.58L4.46 18.78L10.28 18.78L10.28 15.46L9.25 15.46L9.07 15.71L8.83 15.71L8.74 15.62L8.12 15.46L7.32 15.12L7.21 15.17L7.03 15.5L6.92 15.5L6.82 15.38L6.5 15.21L6.16 14.92L5.75 14.92L5.57 15.46L5.38 15.46ZM13.29 13.83L13.29 15.7L16.7 15.7L16.7 13.83ZM3 13.25L3 13.99L5.41 13.99L5.41 13.25ZM25 12L25 12.74L26.99 12.74L26.99 12ZM15 11.04L15 11.99L17.7 11.99L17.7 11.04ZM13.29 8.29L13.29 9.45L15.7 9.45L15.7 8.29ZM17.17 8.21L17.17 10.03L18.25 11.17L18.25 12.16L18.17 12.21L17.17 14.21L17.17 15.78L20.78 15.78L20.78 8.21ZM3.21 5.46L3.21 10.78L8.78 10.78L8.78 8.5L7.88 8.5L7.07 7.66L7.07 7.58L5.83 7.58L4.78 6.57L4.78 5.92L4.41 5.57L4.32 5.42ZM3.29 3.29L3.29 4.91L5.78 4.91L5.78 3.29ZM27.78 3.21L22.21 3.21L22.21 3.41L22.83 4.03L23.08 3.74L23.57 3.74L23.92 4.36L24.08 4.54L24.08 4.99L24.58 5.17L24.58 5.32L24.21 6L24.21 6.16L24.33 6.29L24.32 6.46L23 6.46L23 9.99L24.99 9.99L25 6.45L25.32 6.45L25.62 6.07L25.82 6.07L26.54 6.45L27.78 6.45Z",
    dark: "M18.62 8.21L18.62 10.24L20.78 10.24L20.78 8.21Z",
    dashed: [],
    walls:
      "M3.04 3.15H9.04M11.49 3.15H17.04M22.21 3.15H28.05M13.04 8.15H21.05M3.04 10.94H9.04M13.04 15.94H21.05M4 18.94H10.54M22.34 18.94H27.04M3.15 3.04V11.04M8.94 3.04V11.04M10.44 14.62V19.05M11.6 3.04V5.92M13.15 8.04V16.05M20.94 8.04V16.05M22.44 17.5V19.05M27.94 3.04V6.83",
    doors:
      "M25.33 3.15H27.21M3.58 10.94H4.75M10.44 16.75V18.62M20.94 10.46V12.38",
    labels: [
      ["A", 4.62, 9.4],
      ["B", 19.42, 11.5],
      ["C", 7.58, 17.25],
      ["D", 26.12, 4.62],
      ["E", 12.08, 3.62],
      ["F", 22.96, 18.38],
      ["G", 16.5, 18.5],
      ["H", 16.35, 11.52],
      ["I", 24.02, 8.23],
      ["J", 4.19, 13.62],
      ["K", 26, 12.38],
      ["L", 15, 14.79],
      ["M", 4.54, 4.08],
      ["N", 14.5, 8.88],
    ],
    obj: [
      [24.25, 11, 0],
      [7, 9, 2],
      [15, 12.75, 1],
    ],
  },
  {
    id: "volkus-2025-5",
    kz: "volkus",
    n: 5,
    set: "ao2025",
    s1: "bottom",
    depth: 3,
    fill: "M17.21 20.08L17.21 21.7L19.7 21.7L19.7 20.08ZM6 18L6 18.99L8.99 18.99L8.99 18ZM14.21 14.21L14.21 16.49L15.16 16.53L15.92 17.41L17.16 17.41L18.21 18.42L18.21 19.07L18.67 19.57L19.78 19.57L19.78 14.21L19.42 14.21L19.41 14.29L19.04 14.29L19.03 14.21L18.62 14.21L18.61 14.29L18.25 14.29L18.24 14.21ZM11.29 11L11.29 11.99L13.99 11.99L13.99 11ZM3.83 10.21L3.83 11.24L4.08 11.42L4.08 11.66L4 11.75L3.62 12.95L3.57 13L2 13L2 13.74L3.67 13.75L3.67 13.86L3.29 14.33L3.29 14.74L3.83 14.92L3.83 15.11L3.5 16.03L4.66 16.03L5.08 15.66L5.28 15.66L5.96 16.03L7.16 16.03L7.16 10.21ZM22.42 8.54L22.42 11.78L27.99 11.78L27.99 11.58L27.36 11.04L27.11 11.25L26.67 11.25L26.11 10.41L26.11 10L25.61 9.82L25.66 9.54L25.95 8.91L25.91 8.71L25.57 9L25 9.04L24.79 8.96L24.66 8.79L24.57 8.92L24.38 8.92L23.66 8.54ZM17 7.46L17 10.99L18.99 10.99L18.99 7.46ZM7.21 4.17L7.21 7.78L14.78 7.78L14.78 4.17L12.96 4.17L11.82 5.25L10.83 5.25L10.78 5.17L8.78 4.17ZM3 3L3 3.74L4.99 3.74L4.99 3ZM13.54 0.29L13.54 2.7L14.7 2.7L14.7 0.29ZM7.29 0.29L7.29 3.7L9.16 3.7L9.16 0.29Z",
    dark: "M12.75 5.62L12.75 7.78L14.78 7.78L14.78 5.62Z",
    dashed: [[2, 13, 2.5, 0.75]],
    walls:
      "M7.04 0.15H15.04M20.5 3.15H26.04M7.04 7.94H15.04M3 10.15H7.42M22.25 11.94H28M14.04 14.15H20.05M23 18.94H27.71M14.04 21.94H20.05M7.15 0.04V8.04M7.31 10.04V16.54M14.15 14.04V21.96M14.94 0.04V8.04M19.94 14.04V21.96M20.6 3.04V5.92M22.35 8.21V12.04M23.1 17.5V19.05",
    doors: "M10.62 7.94H12.54M5.12 10.15H7M23 11.94H24.88M18.25 14.15H19.42",
    labels: [
      ["A", 17.25, 15.98],
      ["B", 11.46, 6.92],
      ["C", 5.58, 11.79],
      ["D", 22.83, 11.38],
      ["E", 21.08, 3.62],
      ["F", 23.62, 18.38],
      ["G", 7.5, 18.5],
      ["H", 12.65, 11.5],
      ["I", 18.02, 9.23],
      ["J", 3.19, 13.38],
      ["K", 4, 3.38],
      ["L", 8.21, 2],
      ["M", 18.46, 20.92],
      ["N", 14.12, 1.5],
    ],
    obj: [
      [15, 11, 0],
      [25.25, 8.25, 2],
      [5.25, 14, 1],
    ],
  },
  {
    id: "volkus-2025-6",
    kz: "volkus",
    n: 6,
    set: "ao2025",
    s1: "bottom",
    depth: 3,
    fill: "M2 18.25L2 18.99L4.41 18.99L4.41 18.25ZM25.29 17.54L25.29 18.7L27.7 18.7L27.7 17.54ZM2.29 12.21L2.29 14.7L3.91 14.7L3.91 12.21ZM24.29 11.29L24.29 13.16L27.7 13.16L27.7 11.29ZM20.21 11.21L20.21 18.78L23.82 18.78L23.82 16.96L22.74 15.82L22.74 14.83L22.82 14.78L23.82 12.78L23.82 11.21ZM9.78 9.21L7.5 9.21L7.5 10.11L6.66 10.92L6.58 10.92L6.58 12.16L6.49 12.25L4.46 12.25L4.46 12.99L5.66 12.99L5.67 13.11L5.57 13.21L4.92 13.21L4.42 13.67L4.42 14.78L9.78 14.78ZM13.46 8.21L13.46 9.24L13.71 9.42L13.71 9.66L13.58 9.88L13.25 10.95L11.96 10.96L11.96 14.57L14.03 14.57L14.03 14.04L14.28 14.03L14.71 13.66L14.91 13.66L14.96 13.74L15.07 13.74L15.58 14.03L16.78 14.03L16.78 8.21ZM20 7L20 7.99L22.99 7.99L22.99 7ZM21.21 3.21L21.21 3.41L21.83 4.03L22.08 3.74L22.57 3.74L22.92 4.36L23.08 4.54L23.08 4.99L23.58 5.17L23.58 5.32L23.21 6L23.21 6.16L23.42 6.45L24.32 6.45L24.62 6.07L24.82 6.07L25.54 6.45L26.78 6.45L26.78 3.21ZM14 3L14 3.99L16.7 3.99L16.7 3Z",
    dark: "M20.21 16.75L20.21 18.78L22.36 18.78L22.36 16.75Z",
    dashed: [
      [12, 11, 2, 3.5],
      [4.5, 12.25, 2, 0.75],
    ],
    walls:
      "M5.04 3.15H10.58M21.21 3.15H27.05M12.62 8.15H17.05M2.04 9.15H10.04M20.05 11.15H28.05M2.04 14.94H10.04M9.34 18.94H14.04M20.05 18.94H28.05M2.15 9.04V15.04M5.15 3.04V5.92M9.44 17.5V19.05M9.94 9.04V15.04M16.94 8.04V14.54M20.15 11.04V19.05M26.94 3.04V6.83M27.94 11.04V19.05",
    doors:
      "M24.33 3.15H26.21M14.75 8.15H16.62M9.94 13.25V14.42M20.15 14.62V16.54",
    labels: [
      ["A", 8.02, 12.25],
      ["B", 21.58, 15.46],
      ["C", 14.92, 9.25],
      ["D", 25.12, 4.62],
      ["E", 5.62, 3.62],
      ["F", 9.96, 18.38],
      ["G", 21.5, 7.5],
      ["H", 15.35, 3.5],
      ["I", 13.02, 12.77],
      ["J", 3.19, 18.62],
      ["K", 5.46, 12.62],
      ["L", 26, 12.25],
      ["M", 3.08, 13.46],
      ["N", 26.5, 18.12],
    ],
    obj: [
      [15, 11, 0],
      [23.75, 8.25, 2],
      [7, 13.75, 1],
    ],
  },
  {
    id: "volkus-example-3",
    kz: "volkus",
    n: 3,
    set: "example",
    s1: "right",
    depth: 6,
    fill: "M11.25 19.96L11.25 21.91L11.95 21.91L11.95 19.96ZM16.08 17L16.04 19.99L17.03 19.99L17.03 17.04ZM3.25 16.75L3.25 18.57L6.66 18.57L6.66 16.71ZM19 14.04L19 16.41L19.66 16.41L19.7 14.04ZM23.91 13.38L23.71 13.38L23.71 13.45L23.62 13.46L23.08 14L23.08 14.07L23.38 14.29L23.38 14.74L22.53 15.25L22.17 15.25L22.08 15.33L21.95 15.79L21.83 15.79L21.07 15.38L20.96 15.38L20.67 15.58L20.67 16.53L21.04 16.83L21.04 16.99L20.67 17.71L20.67 18.95L23.91 18.95ZM3.25 11.25L3.25 12.36L5.66 12.36L5.61 11.25ZM7.25 11.17L7.21 13.03L8.29 14.17L8.29 15.07L8.21 15.12L7.96 15.62L7.96 15.74L7.88 15.79L7.21 17.12L7.21 18.74L10.78 18.74L10.74 14.92L10.78 14.58L10.95 14.57L10.74 14.49L10.78 11.17ZM25.17 5.38L25.17 7.82L26.74 7.82L26.74 7.04L26.86 7.03L26.86 6.96L26.74 6.95L26.74 5.38ZM24.49 5.25L19.25 5.25L19.21 7.49L19.29 10.86L21.45 10.82L21.45 9.88L22.36 9.07L22.36 7.83L22.91 7.32L22.92 7.24L22.99 7.24L23.24 6.99L23.25 6.91L23.32 6.91L23.38 6.78L24.03 6.78L24.49 6.32ZM9 3.38L9 4.57L9.38 5L9.38 5.16L9.17 5.57L9.08 5.62L9.08 5.74L9 5.79L9 7.07L14.78 7.07L14.78 6.25L14.99 6.24L14.78 6.2L14.78 3.75L13.75 3.75L13.57 4L13.42 4L13.2 3.88L11.82 3.42L11.71 3.46L11.57 3.71L11.38 3.71L10.74 3.21L10.25 3.25L10.11 3.71L9.92 3.71ZM20.62 2L20.62 3.95L24.11 3.95L24.11 2ZM11.08 0.04L11.04 2.7L11.95 2.7L11.95 0.08Z",
    dark: "M8.62 11.17L8.62 13.16L10.78 13.16L10.78 11.17Z",
    dashed: [],
    walls:
      "M19 5.15H27.05M4.5 6.6H6M8.5 7.19H15.01M13.04 10.06H16M19 10.94H27.05M2.92 11.06H11.01M2.92 18.85H11.01M20.29 19.06H24.09M3.02 10.96V18.95M5.9 2.08V6.71M10.9 10.96V18.95M14.9 3V7.29M15.9 9.96V15.5M19.1 5.04V11.04M23.98 13.38V19.16M26.94 5.04V11.04",
    doors: "M10.9 13.42V15.25M14.9 5.08V7.38M19.1 5.75V7.46M23.98 16.5V18.42",
    labels: [
      ["A", 20.69, 8.04],
      ["B", 9.5, 14.31],
      ["C", 12.02, 5.48],
      ["D", 22.6, 17.46],
      ["E", 15.42, 10.58],
      ["F", 5.42, 6.12],
      ["G", 16.54, 18.52],
      ["H", 11.5, 1.4],
      ["I", 22.38, 3],
      ["J", 19.35, 15.21],
      ["K", 11.6, 20.96],
      ["L", 4.98, 17.73],
      ["M", 25.94, 6.6],
      ["N", 4.48, 11.81],
    ],
    obj: [
      [15, 11, 0],
      [11.25, 3.75, 2],
      [19, 18.25, 1],
    ],
  },
];
const W = 30,
  H = 22;
const SIDE = { 0: "#ff6a13", 1: "#c8372d", 2: "#3d6fd1" };
const OPPOSITE = { left: "right", right: "left", top: "bottom", bottom: "top" };
export const layoutById = (id) => LAYOUTS.find((l) => l.id === id) || null;
export function layoutName(l) {
  if (typeof l === "string") l = layoutById(l);
  if (!l) return "";
  return t(l.set === "example" ? "kz_example" : "kz_map").replace("{n}", l.n);
}
// [x, y, w, h] of the strip of depth d along a board edge.
function strip(edge, d) {
  if (edge === "left") return [0, 0, d, H];
  if (edge === "right") return [W - d, 0, d, H];
  if (edge === "top") return [0, 0, W, d];
  return [0, H - d, W, d];
}
/* Drop zones and territories of both players; swap — player 1 takes the other drop zone. */
export function zones(l, swap = false) {
  const half = l.s1 === "left" || l.s1 === "right" ? W / 2 : H / 2,
    e1 = swap ? OPPOSITE[l.s1] : l.s1;
  return [1, 2].map((side) => {
    const edge = side === 1 ? e1 : OPPOSITE[e1];
    return { side, edge, drop: strip(edge, l.depth), half: strip(edge, half) };
  });
}
const rect = ([x, y, w, h], attrs) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" ${attrs}/>`;
function zoneEdge(z) {
  const [x, y, w, h] = z.drop;
  const [x1, y1, x2, y2] =
    z.edge === "left"
      ? [x + w, 0, x + w, H]
      : z.edge === "right"
        ? [x, 0, x, H]
        : z.edge === "top"
          ? [0, y + h, W, y + h]
          : [0, y, W, y];
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${SIDE[z.side]}" stroke-width="0.07"/>`;
}
/* Static layer under the tokens (and in the PNG export): zones, centre lines, terrain, doors, letters, objectives. */
export function layoutSvg(id, swap = false) {
  const l = layoutById(id);
  if (!l) return "";
  const across = l.s1 === "left" || l.s1 === "right",
    side = (s) => SIDE[swap && s ? 3 - s : s],
    zs = zones(l, swap),
    vertical = `x1="15" y1="0" x2="15" y2="${H}"`,
    horizontal = `x1="0" y1="11" x2="${W}" y2="11"`;
  const parts = [
    ...zs.map(
      (z) =>
        rect(z.half, `fill="${SIDE[z.side]}" fill-opacity="0.07"`) +
        rect(z.drop, `fill="${SIDE[z.side]}" fill-opacity="0.2"`),
    ),
    ...zs.map(zoneEdge),
    // the territories meet at the dashed centre line
    `<line ${across ? vertical : horizontal} stroke="#8a94a3" stroke-width="0.05" stroke-dasharray="0.35 0.25"/>`,
    `<line ${across ? horizontal : vertical} stroke="#3c4550" stroke-width="0.04"/>`,
    `<path d="${l.fill}" fill="#66766d"/>`,
    l.dark
      ? `<path d="${l.dark}" fill="#2f4639" stroke="#93a89b" stroke-width="0.04"/>`
      : "",
    ...l.dashed.map((r) =>
      rect(
        r,
        'fill="none" stroke="#e6ebf0" stroke-width="0.06" stroke-dasharray="0.25 0.18"',
      ),
    ),
    `<path d="${l.walls}" fill="none" stroke="#dfe5ec" stroke-width="0.21"/>`,
    // a door is the dashed part of a wall
    `<path d="${l.doors}" fill="none" stroke="#14181d" stroke-width="0.23" stroke-dasharray="0.2 0.16"/>`,
    ...l.labels.map(
      ([c, x, y]) =>
        `<g transform="translate(${x} ${y})"><rect x="-0.33" y="-0.33" width="0.66" height="0.66" rx="0.08" fill="#3b4147" stroke="#8a94a3" stroke-width="0.03"/><text y="0.16" font-size="0.44" font-weight="700" text-anchor="middle" fill="#fff">${c}</text></g>`,
    ),
    ...l.obj.map(
      ([x, y, s]) =>
        `<g class="kz-obj" transform="translate(${x} ${y})"><circle r="0.79" fill="${side(s)}" fill-opacity="0.16" stroke="${side(s)}" stroke-width="0.1"/><circle r="0.28" fill="${side(s)}"/></g>`,
    ),
  ];
  return `<g class="kz" pointer-events="none" font-family="sans-serif">${parts.join("")}</g>`;
}
/* <select> of the terrain presets for the new-board and settings forms ("" — none). */
export function layoutSelect(value = "") {
  const ao = LAYOUTS.filter((l) => l.set === "ao2025"),
    other = LAYOUTS.filter((l) => l.set !== "ao2025"),
    group = (label, list) =>
      `<optgroup label="${esc(label)}">${list.map((l) => `<option value="${l.id}" ${l.id === value ? "selected" : ""}>${esc(layoutName(l))}</option>`).join("")}</optgroup>`;
  return `<label>${esc(t("map_layout"))}<select name="layout" data-layout><option value="">${esc(t("map_layoutNone"))}</option>${group(t("kz_groupAo"), ao)}${group(t("kz_groupOther"), other)}</select></label>`;
}
const swatch = (body) =>
  `<svg class="kz-swatch" viewBox="0 0 1.6 1" aria-hidden="true">${body}</svg>`;
/* Key under the board: what the letters and the symbols mean, where the layout comes from. */
export function layoutLegend(id) {
  const l = layoutById(id);
  if (!l) return "";
  const keys = [
    ["A, B", "kz_stronghold"],
    ["L, M, N", "kz_strongholdParts"],
    ["C, D", "kz_largeRuin"],
    ["E, F", "kz_smallRuin"],
    ["G, H", "kz_heavyRubble"],
    ["I, J, K", "kz_lightRubble"],
  ];
  const symbols = [
    [
      `<rect width="1.6" height="1" fill="#c8372d" fill-opacity="0.35"/><rect x="0.8" width="0.8" height="1" fill="#3d6fd1" fill-opacity="0.35"/>`,
      "kz_zones",
    ],
    [`<rect width="1.6" height="1" fill="#66766d"/>`, "kz_terrain"],
    [
      `<rect width="1.6" height="1" fill="#2f4639" stroke="#93a89b" stroke-width="0.08"/>`,
      "kz_upper",
    ],
    [
      `<line x1="0" y1="0.5" x2="1.6" y2="0.5" stroke="#dfe5ec" stroke-width="0.25"/>`,
      "kz_wall",
    ],
    [
      `<line x1="0" y1="0.5" x2="1.6" y2="0.5" stroke="#dfe5ec" stroke-width="0.25"/><line x1="0" y1="0.5" x2="1.6" y2="0.5" stroke="#14181d" stroke-width="0.27" stroke-dasharray="0.2 0.16"/>`,
      "kz_door",
    ],
    [
      `<rect x="0.1" y="0.1" width="1.4" height="0.8" fill="none" stroke="#e6ebf0" stroke-width="0.07" stroke-dasharray="0.25 0.18"/>`,
      "kz_beneath",
    ],
    [
      `<circle cx="0.4" cy="0.5" r="0.32" fill="#c8372d" fill-opacity="0.3" stroke="#c8372d" stroke-width="0.08"/><circle cx="1.2" cy="0.5" r="0.32" fill="#ff6a13" fill-opacity="0.3" stroke="#ff6a13" stroke-width="0.08"/>`,
      "kz_objectives",
    ],
  ];
  return `<details class="kz-legend" open><summary>${esc(t("kz_legend"))} · ${esc(layoutName(l))}</summary><ul class="kz-keys">${keys.map(([k, v]) => `<li><b>${k}</b> ${esc(t(v))}</li>`).join("")}</ul><ul class="kz-symbols">${symbols.map(([s, k]) => `<li>${swatch(s)}<span>${esc(t(k))}</span></li>`).join("")}</ul><p class="muted small">${esc(t(l.set === "example" ? "kz_sourceExample" : "kz_sourceAo"))} <a href="#core/volkus">${esc(t("kz_rules"))}</a></p></details>`;
}
