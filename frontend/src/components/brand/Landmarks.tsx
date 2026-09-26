import type { ReactNode, SVGProps } from "react";

// Hairline drawings of Chișinău landmarks, echoing the skyline art in the margins of chisinau.md.
// Every shape stands on y = 0 so they can be placed along one ground line.

type ArtProps = SVGProps<SVGSVGElement>;

// Horizontal lines (floors, courses) from `from` up to `to`, every `step` units.
function courses(x1: number, x2: number, from: number, to: number, step: number) {
  let d = "";
  for (let y = from; y >= to; y -= step) d += `M${x1} ${y}H${x2}`;
  return d;
}

// Catedrala Mitropolitană „Nașterea Domnului”: hexastyle portico, drum and dome. 200 wide.
function CathedralShape() {
  const columns = [52, 71, 90, 110, 129, 148];
  const drumWindows = [80, 90, 100, 110, 120];
  return (
    <g>
      <path d="M14 0H186M20 -6H180M26 -12H174" />
      <path d="M30 -12V-86H170V-12M34 -34V-60A3 3 0 0 1 40 -60V-34ZM160 -34V-60A3 3 0 0 1 166 -60V-34Z" />
      <path d="M44 -86V-94H156V-86ZM40 -94L100 -118L160 -94ZM55 -97L100 -115L145 -97Z" />
      <path d={columns.map((x) => `M${x - 3} -12V-86M${x + 3} -12V-86M${x - 5} -82H${x + 5}`).join("")} />
      <path d="M94 -12V-36A6 6 0 0 1 106 -36V-12" />
      <path d="M70 -106V-146M130 -106V-146M66 -146H134M70 -142H130" />
      <path d={drumWindows.map((x) => `M${x - 2.5} -122V-133.5A2.5 2.5 0 0 1 ${x + 2.5} -133.5V-122Z`).join("")} />
      <path d="M68 -146A32 34 0 0 1 132 -146M84 -146Q87 -168 95 -178M116 -146Q113 -168 105 -178" />
      <path d="M94 -179V-189M106 -179V-189M92 -189H108M93 -189A7 6 0 0 1 107 -189M100 -195V-208M96 -203H104" />
    </g>
  );
}

// The cathedral's four-tier bell tower. 60 wide.
function BellTowerShape() {
  return (
    <g>
      <path d="M8 0V-60H52V0M5 -60V-64H55V-60ZM24 0V-24A6 6 0 0 1 36 -24V0" />
      <path d="M12 -64V-108H48V-64M9 -108V-112H51V-108ZM24 -72V-94A6 6 0 0 1 36 -94V-72ZM16 -64V-108M44 -64V-108" />
      <path d="M16 -112V-146H44V-112M13 -146V-150H47V-146ZM25 -118V-136A5 5 0 0 1 35 -136V-118Z" />
      <path d="M19 -150V-172H41V-150M30 -161V-165M30 -161L33 -159.5" />
      <circle cx="30" cy="-161" r="6" />
      <path d="M17 -172H43M18 -172A12 11 0 0 1 42 -172M30 -183V-200M26 -195H34" />
    </g>
  );
}

// Arcul de Triumf (the Holy Gates), with the clock in its attic. 160 wide.
function TriumphalArchShape() {
  const columns = [30, 44, 116, 130];
  return (
    <g>
      <path d="M20 0V-110H140V0M14 -110V-116H146V-110ZM20 -104H140" />
      <path d="M40 -116V-140H120V-116M36 -140V-144H124V-140ZM64 -144V-150H96V-144" />
      <circle cx="80" cy="-128" r="7" />
      <path d="M80 -128V-133M80 -128L84 -126" />
      <path d="M58 0V-60A22 22 0 0 1 102 -60V0M77 -81L78 -89H82L83 -81M47 -60H58M102 -60H113M20 -6H58M102 -6H140" />
      <path d={columns.map((x) => `M${x - 3} -6V-104M${x + 3} -6V-104M${x - 5} -100H${x + 5}`).join("")} />
    </g>
  );
}

// Porțile Orașului: the twin towers at the city's entrance on bd. Dacia. 200 wide.
function CityGatesShape() {
  return (
    <g>
      <path d="M36 0V-200H78V0M16 0V-150H36M46 -200V-210H68V-200M57 -4V-196" />
      <path d={courses(36, 78, -11, -190, 11) + courses(16, 36, -11, -140, 11)} />
      <path d="M122 0V-200H164V0M184 0V-150H164M132 -200V-210H154V-200M143 -4V-196" />
      <path d={courses(122, 164, -11, -190, 11) + courses(164, 184, -11, -140, 11)} />
    </g>
  );
}

function Tree({ x, tall = false }: { x: number; tall?: boolean }) {
  const [rx, ry] = tall ? [7, 22] : [12, 14];
  return (
    <g>
      <path d={`M${x} 0V-12`} />
      <ellipse cx={x} cy={-12 - ry} rx={rx} ry={ry} />
    </g>
  );
}

function Block({ x, width, height }: { x: number; width: number; height: number }) {
  return <path d={`M${x} 0V${-height}H${x + width}V0` + courses(x, x + width, -10, 6 - height, 10)} />;
}

function LineArt({ className = "", children, ...props }: ArtProps & { children: ReactNode }) {
  return (
    <svg
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`line-art ${className}`}
      {...props}
    >
      {children}
    </svg>
  );
}

export function Skyline(props: ArtProps) {
  return (
    <LineArt viewBox="0 -216 1200 218" {...props}>
      <path d="M0 0H1200" />
      <Tree x={18} />
      <Block x={40} width={44} height={96} />
      <g transform="translate(96 0)">
        <CityGatesShape />
      </g>
      <Tree x={312} tall />
      <Tree x={334} />
      <g transform="translate(356 0)">
        <TriumphalArchShape />
      </g>
      <Tree x={534} />
      <Tree x={556} tall />
      <g transform="translate(574 0)">
        <CathedralShape />
      </g>
      <g transform="translate(784 0)">
        <BellTowerShape />
      </g>
      <Tree x={866} tall />
      <Tree x={890} />
      <Block x={912} width={52} height={120} />
      <Block x={972} width={40} height={74} />
      <Block x={1020} width={60} height={150} />
      <Tree x={1100} />
      <Block x={1122} width={46} height={88} />
      <Tree x={1184} tall />
    </LineArt>
  );
}

export function CathedralArt(props: ArtProps) {
  return (
    <LineArt viewBox="-4 -212 292 214" {...props}>
      <path d="M-4 0H288" />
      <CathedralShape />
      <g transform="translate(206 0)">
        <BellTowerShape />
      </g>
      <Tree x={276} tall />
    </LineArt>
  );
}

export function TriumphalArchArt(props: ArtProps) {
  return (
    <LineArt viewBox="0 -154 196 156" {...props}>
      <path d="M0 0H196" />
      <TriumphalArchShape />
      <Tree x={178} />
    </LineArt>
  );
}

export function CityGatesArt(props: ArtProps) {
  return (
    <LineArt viewBox="-24 -214 224 216" {...props}>
      <path d="M-24 0H200" />
      <Tree x={-8} tall />
      <CityGatesShape />
    </LineArt>
  );
}

// The app's mark: the cathedral's domed drum and cross, drawn to sit on a blue tile.
export function CityEmblem(props: ArtProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M6 27H26M9 27V19M23 27V19M8 19H24M13 27V23M16 27V23M19 27V23M9 19A7 7.5 0 0 1 23 19" />
      <path d="M16 11.5V4M13.5 6.5H18.5" stroke="currentColor" className="text-accent" />
    </svg>
  );
}
