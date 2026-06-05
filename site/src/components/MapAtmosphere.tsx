import { useEffect, useRef } from "react";

/**
 * A very faint animated "atmosphere" rendered over the map: a slowly drifting
 * bloom spotlight, gentle brightness bubbling, and slow organized waves of
 * color. One fullscreen fragment-shader quad (raw WebGL, no deps) -> negligible
 * GPU cost. Screen-blended so it only ever *adds* a little light. Decorative
 * only: pointer-events none, so it never intercepts map interaction.
 */
const FRAG = `
precision highp float;
uniform float uTime;
uniform vec2 uRes;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float noise(vec2 p){
  vec2 i=floor(p), f=fract(p);
  float a=hash(i), b=hash(i+vec2(1.,0.)), c=hash(i+vec2(0.,1.)), d=hash(i+vec2(1.,1.));
  vec2 u=f*f*(3.-2.*f);
  return mix(mix(a,b,u.x), mix(c,d,u.x), u.y);
}
void main(){
  vec2 uv = gl_FragCoord.xy / uRes;
  float asp = uRes.x / uRes.y;
  float t = uTime * 0.045;                       // slow

  // --- drifting bloom spotlights (Lissajous paths) ---
  // The raw paths cross the middle; we push each offset radially outward so it
  // never enters the central circle (MINR) -- the blooms ride the edges, which
  // reads much prettier than parking light over the dense center.
  vec2 p = vec2(uv.x*asp, uv.y);
  const float MINR = 0.30;                        // exclude the middle ~35%
  // One slowly-rotating, gently elliptical direction; the two blooms sit on
  // OPPOSITE sides of center (o2 = -dir) so they never crowd the same edge.
  float ang = t*0.6;
  vec2 dir = normalize(vec2(cos(ang), sin(ang*1.08)));
  vec2 o1 =  dir * max(0.36 + 0.05*sin(t*0.9), MINR);
  vec2 o2 = -dir * max(0.40 + 0.05*cos(t*0.7), MINR);
  vec2 c1 = vec2((0.5 + o1.x)*asp, 0.5 + o1.y);
  vec2 c2 = vec2((0.5 + o2.x)*asp, 0.5 + o2.y);
  float b1 = smoothstep(0.55, 0.0, length(p - c1));
  float b2 = smoothstep(0.65, 0.0, length(p - c2));

  // --- gentle brightness "bubbling" (low-freq drifting noise) ---
  float bub = noise(uv*2.6 + vec2(t*0.5, -t*0.35))*0.6 + noise(uv*5.0 - t*0.25)*0.25;

  // --- organized slow saturation waves (diagonal sine bands) ---
  float w = 0.5 + 0.5*sin((uv.x + uv.y)*3.5 - t*1.3);

  vec3 warm = vec3(1.0, 0.84, 0.58);
  vec3 cool = vec3(0.46, 0.68, 1.0);
  vec3 col = warm*b1*0.55 + cool*b2*0.45 + mix(cool, warm, w)*bub*0.18;

  gl_FragColor = vec4(col * 0.5, 1.0);           // screen-blended, kept faint
}`;

const VERT = `attribute vec2 a; void main(){ gl_Position = vec4(a, 0.0, 1.0); }`;

export function MapAtmosphere({ variant }: { variant?: "soft" | "screen" } = {}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { premultipliedAlpha: false, antialias: false });
    if (!gl) return;

    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const uTime = gl.getUniformLocation(prog, "uTime");
    const uRes = gl.getUniformLocation(prog, "uRes");

    let raf = 0;
    let start = 0;
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5); // cap for perf
      const w = canvas.clientWidth, h = canvas.clientHeight;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();

    const frame = (ts: number) => {
      if (!start) start = ts;
      gl.uniform1f(uTime, (ts - start) / 1000);
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      // NOTE: do NOT loseContext() here -- in dev StrictMode the effect
      // unmounts/remounts, and a canvas reuses its (now-lost) context, leaving
      // a dead overlay. Let GC reclaim the context on real unmount.
    };
  }, []);

  return (
    <canvas
      ref={ref}
      className={"exploremap__atmosphere" + (variant === "screen" ? " exploremap__atmosphere--screen" : "")}
      aria-hidden="true"
    />
  );
}
