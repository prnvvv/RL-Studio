// WebGL point renderer for the landing scene (no three.js).
//
// Portability notes (these are the things software GL forgives and real
// drivers do not):
//  - smoothstep() is only used with edge0 < edge1 (reversed edges are
//    undefined in GLSL); decreasing falloffs use `1.0 - smoothstep(...)`.
//  - precision is explicit; pow() bases are clamped non-negative.
//  - output is premultiplied and blended additively (ONE, ONE).
//  - after the scene is assembled the drawing buffer is read back once; an
//    all-transparent result is reported so the caller can fall back to 2D.

import type { BackendCallbacks, Logger, RenderBackend } from './backendTypes'
import { buildParticles, getSceneLayout, PARTICLE_STRIDE } from './sceneGeometry'
import type { SceneState } from './sceneState'
import { createDisplacementField } from './displacementField'

const PARTICLE_VERTEX = /* glsl */ `
precision highp float;
attribute vec2 aBase;
attribute vec2 aScatter;
attribute vec3 aMeta; // size, alpha, seed
attribute vec2 aDisp; // CPU spring displacement
uniform float uTime;
uniform float uAssemble;
uniform float uAspect;
uniform float uPxScale;
uniform float uMotion;
uniform float uPushGain; // brightness per unit of displacement
uniform vec2 uMouse;
uniform float uMouseAmt;
uniform vec2 uAgent;
uniform float uAgentBoost;
uniform vec2 uHazard;
uniform float uHazardBoost;
uniform float uRippleRadius;
uniform float uRippleAmt;
varying float vAlpha;
varying float vBright;

// 1 at d = 0, 0 at d >= radius (smoothstep with increasing edges only).
float falloff(float radius, float d) {
  return 1.0 - smoothstep(0.0, radius, d);
}

void main() {
  float seed = aMeta.z;
  float t = clamp((uAssemble - seed * 0.4) / 0.6, 0.0, 1.0);
  float eased = 1.0 - pow(max(1.0 - t, 0.0), 3.0);
  vec2 p = mix(aScatter, aBase, eased);

  // Idle shimmer / drift.
  p += 0.0022 * uMotion * vec2(sin(uTime * 0.7 + seed * 61.0), cos(uTime * 0.55 + seed * 47.0));

  float bright = 1.0;

  // Cursor repulsion comes from the CPU spring field; lift and brighten here.
  p += aDisp;
  float push = length(aDisp);
  p.y -= min(push * 0.45, 0.03); // slight z-lift
  bright += min(push * uPushGain, 2.2);
  vec2 d = p - uMouse;
  d.x *= uAspect;
  bright += falloff(0.13, length(d)) * uMouseAmt * 0.8;

  // Touch ripple: an expanding ring that pushes particles outward.
  vec2 r = p - vec2(0.5);
  r.x *= uAspect;
  float rlen = length(r);
  float rf = falloff(0.07, abs(rlen - uRippleRadius)) * uRippleAmt;
  vec2 rdir = r / (rlen + 0.0001);
  rdir.x /= uAspect;
  p += rdir * rf * 0.035;
  bright += rf;

  // Particles light up near the agent (more on hover) and on hazard hover.
  vec2 da = p - uAgent;
  da.x *= uAspect;
  bright += falloff(0.09, length(da)) * (1.3 + uAgentBoost * 2.2);
  vec2 dh = p - uHazard;
  dh.x *= uAspect;
  bright += falloff(0.1, length(dh)) * uHazardBoost * 1.6;

  // Soft fade towards the scene edges so there is no hard bounding box.
  vec2 e = (aBase - 0.5) * 2.0;
  float vignette = 1.0 - smoothstep(0.62, 1.0, length(e * vec2(0.92, 1.0)));

  float twinkle = 0.88 + 0.12 * sin(uTime * 1.3 * uMotion + seed * 90.0);
  vAlpha = aMeta.y * t * vignette * twinkle;
  vBright = bright;
  gl_Position = vec4(p.x * 2.0 - 1.0, 1.0 - p.y * 2.0, 0.0, 1.0);
  gl_PointSize = max(aMeta.x * uPxScale * (1.0 + min(push * 10.0, 0.7)), 1.0);
}
`

const PARTICLE_FRAGMENT = /* glsl */ `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying float vAlpha;
varying float vBright;

void main() {
  float d = length(gl_PointCoord - 0.5);
  float shape = 1.0 - smoothstep(0.12, 0.5, d);
  float a = clamp(shape * vAlpha * min(vBright, 2.6), 0.0, 1.0);
  gl_FragColor = vec4(vec3(0.94) * a, a);
}
`

// Sprites: soft glows for the agent, path nodes and goal pulse.
const SPRITE_VERTEX = /* glsl */ `
precision highp float;
attribute vec2 aPos;
attribute vec2 aInfo; // size (css px), alpha
uniform float uPxScale;
varying float vAlpha;

void main() {
  vAlpha = aInfo.y;
  gl_Position = vec4(aPos.x * 2.0 - 1.0, 1.0 - aPos.y * 2.0, 0.0, 1.0);
  gl_PointSize = max(aInfo.x * uPxScale, 1.0);
}
`

const SPRITE_FRAGMENT = /* glsl */ `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying float vAlpha;

void main() {
  float d = length(gl_PointCoord - 0.5) * 2.0;
  if (d > 1.0) discard;
  float a = clamp(pow(max(1.0 - d, 0.0), 2.2) * vAlpha, 0.0, 1.0);
  gl_FragColor = vec4(vec3(0.97) * a, a);
}
`

/** Brightness gain per unit of displacement: raised blocks glow less than repelled dust. */
const REPEL_PUSH_GAIN = 28
const TERRAIN_PUSH_GAIN = 11

const MAX_SPRITES = 48
const SPRITE_FLOATS = 4 // x, y, size, alpha
/** Fewer lit pixels than this after assembly is treated as "drew nothing". */
const MIN_LIT_PIXELS = 200
const VERIFY_AFTER_DRAWS = 2

export interface WebGLBackendOptions {
  density: number
  /** Hover raises blocks (Terrain-style) instead of repelling particles. */
  terrain: boolean
  motion: boolean
  debug: boolean
  log: Logger
  callbacks: BackendCallbacks
}

function compile(gl: WebGLRenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type)
  if (!shader) throw new Error('createShader returned null')
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader)
    gl.deleteShader(shader)
    throw new Error(`shader compile failed: ${log}`)
  }
  return shader
}

function link(gl: WebGLRenderingContext, vertex: string, fragment: string): WebGLProgram {
  const program = gl.createProgram()
  if (!program) throw new Error('createProgram returned null')
  const vs = compile(gl, gl.VERTEX_SHADER, vertex)
  const fs = compile(gl, gl.FRAGMENT_SHADER, fragment)
  gl.attachShader(program, vs)
  gl.attachShader(program, fs)
  gl.linkProgram(program)
  gl.deleteShader(vs)
  gl.deleteShader(fs)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program)
    gl.deleteProgram(program)
    throw new Error(`program link failed: ${log}`)
  }
  return program
}

interface Resources {
  particleProgram: WebGLProgram
  spriteProgram: WebGLProgram
  particleBuffer: WebGLBuffer
  dispBuffer: WebGLBuffer
  spriteBuffer: WebGLBuffer
  u: Record<string, WebGLUniformLocation | null>
  sPxScale: WebGLUniformLocation | null
  attr: { base: number; scatter: number; meta: number; disp: number; pos: number; info: number }
}

const UNIFORMS = [
  'uTime',
  'uAssemble',
  'uAspect',
  'uPxScale',
  'uMotion',
  'uPushGain',
  'uMouse',
  'uMouseAmt',
  'uAgent',
  'uAgentBoost',
  'uHazard',
  'uHazardBoost',
  'uRippleRadius',
  'uRippleAmt',
]

/** Returns null (after a console.error) when WebGL cannot be used. */
export function createWebGLBackend(
  canvas: HTMLCanvasElement,
  options: WebGLBackendOptions,
): RenderBackend | null {
  const { log, callbacks, debug } = options

  let gl: WebGLRenderingContext | null
  try {
    gl = canvas.getContext('webgl', {
      alpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: true,
      preserveDrawingBuffer: false,
    })
  } catch (error) {
    console.error('[landing-scene] WebGL context creation threw:', error)
    return null
  }
  if (!gl) {
    console.error('[landing-scene] WebGL is unavailable (getContext returned null).')
    return null
  }
  const context = gl

  const layout = getSceneLayout()
  const particles = buildParticles({ density: options.density })
  const { data, count } = particles
  const field = createDisplacementField(particles, options.terrain)
  const spriteData = new Float32Array(MAX_SPRITES * SPRITE_FLOATS)

  if (debug) {
    const info = context.getExtension('WEBGL_debug_renderer_info')
    log('webgl ready', {
      version: context.getParameter(context.VERSION),
      renderer: info ? context.getParameter(info.UNMASKED_RENDERER_WEBGL) : 'masked',
      pointSizeRange: Array.from(
        context.getParameter(context.ALIASED_POINT_SIZE_RANGE) as Float32Array,
      ),
      particles: count,
    })
  }

  function checkError(stage: string): void {
    const err = context.getError()
    if (err !== context.NO_ERROR) {
      console.warn(`[landing-scene] gl.getError() = 0x${err.toString(16)} after ${stage}`)
    } else if (debug) {
      log(`gl.getError() clean after ${stage}`)
    }
  }

  function init(): Resources {
    const particleProgram = link(context, PARTICLE_VERTEX, PARTICLE_FRAGMENT)
    const spriteProgram = link(context, SPRITE_VERTEX, SPRITE_FRAGMENT)

    const particleBuffer = context.createBuffer()
    const dispBuffer = context.createBuffer()
    const spriteBuffer = context.createBuffer()
    if (!particleBuffer || !dispBuffer || !spriteBuffer) throw new Error('createBuffer failed')

    context.bindBuffer(context.ARRAY_BUFFER, particleBuffer)
    context.bufferData(context.ARRAY_BUFFER, data, context.STATIC_DRAW)
    context.bindBuffer(context.ARRAY_BUFFER, dispBuffer)
    context.bufferData(context.ARRAY_BUFFER, field.displacement, context.DYNAMIC_DRAW)
    context.bindBuffer(context.ARRAY_BUFFER, spriteBuffer)
    context.bufferData(context.ARRAY_BUFFER, spriteData.byteLength, context.DYNAMIC_DRAW)

    const u: Record<string, WebGLUniformLocation | null> = {}
    for (const name of UNIFORMS) u[name] = context.getUniformLocation(particleProgram, name)

    const resources: Resources = {
      particleProgram,
      spriteProgram,
      particleBuffer,
      dispBuffer,
      spriteBuffer,
      u,
      sPxScale: context.getUniformLocation(spriteProgram, 'uPxScale'),
      attr: {
        base: context.getAttribLocation(particleProgram, 'aBase'),
        scatter: context.getAttribLocation(particleProgram, 'aScatter'),
        meta: context.getAttribLocation(particleProgram, 'aMeta'),
        disp: context.getAttribLocation(particleProgram, 'aDisp'),
        pos: context.getAttribLocation(spriteProgram, 'aPos'),
        info: context.getAttribLocation(spriteProgram, 'aInfo'),
      },
    }
    const missing = Object.entries(resources.attr).filter(([, loc]) => loc < 0)
    if (missing.length > 0) {
      throw new Error(`missing attributes: ${missing.map(([name]) => name).join(', ')}`)
    }
    checkError('setup')
    return resources
  }

  let resources: Resources
  try {
    resources = init()
  } catch (error) {
    console.error('[landing-scene] WebGL initialisation failed:', error)
    return null
  }

  let cssWidth = 1
  let pxScale = 1
  let lost = false
  let drawCount = 0
  let verified = false
  let disposed = false
  let firstDrawChecked = false

  const onLost = (event: Event) => {
    event.preventDefault() // allows the context to be restored
    lost = true
    console.warn('[landing-scene] webglcontextlost')
    callbacks.onContextLost()
  }
  const onRestored = () => {
    console.warn('[landing-scene] webglcontextrestored: re-initialising')
    try {
      resources = init()
      lost = false
      verified = false
      drawCount = 0
      callbacks.onContextRestored()
    } catch (error) {
      console.error('[landing-scene] re-initialisation after context restore failed:', error)
      callbacks.onProblem('context restore failed', true)
    }
  }
  canvas.addEventListener('webglcontextlost', onLost)
  canvas.addEventListener('webglcontextrestored', onRestored)

  function bindFloat(
    buffer: WebGLBuffer,
    loc: number,
    size: number,
    stride: number,
    offset: number,
  ) {
    context.bindBuffer(context.ARRAY_BUFFER, buffer)
    context.enableVertexAttribArray(loc)
    context.vertexAttribPointer(loc, size, context.FLOAT, false, stride, offset)
  }

  function verifyDrawn(): void {
    const w = context.drawingBufferWidth
    const h = context.drawingBufferHeight
    if (w === 0 || h === 0) {
      callbacks.onProblem(`drawing buffer is ${w}x${h}`, true)
      return
    }
    const pixels = new Uint8Array(w * h * 4)
    context.readPixels(0, 0, w, h, context.RGBA, context.UNSIGNED_BYTE, pixels)
    let lit = 0
    for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 10) lit += 1
    if (debug) log('readback', { drawingBuffer: [w, h], litPixels: lit })
    if (lit < MIN_LIT_PIXELS) {
      callbacks.onProblem(`WebGL drew nothing (${lit} lit pixels in ${w}x${h} buffer)`, true)
    }
  }

  return {
    kind: 'webgl',
    particleCount: count,
    lastStepMs: 0,

    resize(width, height, dpr) {
      cssWidth = Math.max(1, width)
      const canvasWidth = Math.round(cssWidth * dpr)
      const canvasHeight = Math.round(height * dpr)
      canvas.width = canvasWidth
      canvas.height = canvasHeight
      // Point sizes are authored for a ~780px wide scene.
      pxScale = dpr * Math.min(1.35, Math.max(0.6, cssWidth / 780))
      if (debug) {
        log('resize', {
          css: [width, height],
          canvas: [canvas.width, canvas.height],
          drawingBuffer: [context.drawingBufferWidth, context.drawingBufferHeight],
          dpr,
        })
      }
    },

    draw(state: SceneState, dt: number) {
      if (disposed || lost || canvas.width === 0 || canvas.height === 0) return
      const r = resources

      const t0 = performance.now()
      const moved = field.step(dt, state.mouse, state.mouseAmt, layout.aspect)
      this.lastStepMs = moved ? performance.now() - t0 : 0

      context.viewport(0, 0, context.drawingBufferWidth, context.drawingBufferHeight)
      context.clearColor(0, 0, 0, 0)
      context.clear(context.COLOR_BUFFER_BIT)
      context.enable(context.BLEND)
      context.blendFunc(context.ONE, context.ONE) // premultiplied additive: dust accumulates into glow

      const agent = state.agentPoint()

      context.useProgram(r.particleProgram)
      const stride = PARTICLE_STRIDE * 4
      bindFloat(r.particleBuffer, r.attr.base, 2, stride, 0)
      bindFloat(r.particleBuffer, r.attr.scatter, 2, stride, 8)
      bindFloat(r.particleBuffer, r.attr.meta, 3, stride, 16)
      context.bindBuffer(context.ARRAY_BUFFER, r.dispBuffer)
      if (moved) context.bufferSubData(context.ARRAY_BUFFER, 0, field.displacement)
      context.enableVertexAttribArray(r.attr.disp)
      context.vertexAttribPointer(r.attr.disp, 2, context.FLOAT, false, 0, 0)

      const u = r.u
      context.uniform1f(u.uTime, state.time)
      context.uniform1f(u.uAssemble, state.assemble)
      context.uniform1f(u.uAspect, layout.aspect)
      context.uniform1f(u.uPxScale, pxScale)
      context.uniform1f(u.uMotion, options.motion ? 1 : 0)
      context.uniform1f(u.uPushGain, options.terrain ? TERRAIN_PUSH_GAIN : REPEL_PUSH_GAIN)
      context.uniform2f(u.uMouse, state.mouse.x, state.mouse.y)
      context.uniform1f(u.uMouseAmt, state.mouseAmt)
      context.uniform2f(u.uAgent, agent.x, agent.y)
      context.uniform1f(u.uAgentBoost, state.agentBoost)
      context.uniform2f(u.uHazard, layout.hazard.x, layout.hazard.y)
      context.uniform1f(u.uHazardBoost, state.hazardBoost)
      context.uniform1f(u.uRippleRadius, state.rippleRadius)
      context.uniform1f(u.uRippleAmt, state.rippleAmt)
      context.drawArrays(context.POINTS, 0, count)
      for (const loc of [r.attr.base, r.attr.scatter, r.attr.meta, r.attr.disp]) {
        context.disableVertexAttribArray(loc)
      }

      let n = 0
      state.writeSprites((p, size, alpha) => {
        if (n >= MAX_SPRITES || alpha <= 0.002) return
        const o = n * SPRITE_FLOATS
        spriteData[o] = p.x
        spriteData[o + 1] = p.y
        spriteData[o + 2] = size
        spriteData[o + 3] = alpha
        n += 1
      })
      context.useProgram(r.spriteProgram)
      context.bindBuffer(context.ARRAY_BUFFER, r.spriteBuffer)
      context.bufferSubData(context.ARRAY_BUFFER, 0, spriteData.subarray(0, n * SPRITE_FLOATS))
      const spriteStride = SPRITE_FLOATS * 4
      bindFloat(r.spriteBuffer, r.attr.pos, 2, spriteStride, 0)
      bindFloat(r.spriteBuffer, r.attr.info, 2, spriteStride, 8)
      context.uniform1f(r.sPxScale, pxScale)
      context.drawArrays(context.POINTS, 0, n)
      context.disableVertexAttribArray(r.attr.pos)
      context.disableVertexAttribArray(r.attr.info)

      drawCount += 1
      if (!firstDrawChecked) {
        firstDrawChecked = true
        checkError('first draw')
      }
      if (!verified && state.assemble >= 1 && drawCount >= VERIFY_AFTER_DRAWS) {
        verified = true
        verifyDrawn()
      }
    },

    dispose() {
      if (disposed) return
      disposed = true
      canvas.removeEventListener('webglcontextlost', onLost)
      canvas.removeEventListener('webglcontextrestored', onRestored)
      if (!lost) {
        const r = resources
        context.deleteBuffer(r.particleBuffer)
        context.deleteBuffer(r.dispBuffer)
        context.deleteBuffer(r.spriteBuffer)
        context.deleteProgram(r.particleProgram)
        context.deleteProgram(r.spriteProgram)
      }
      context.getExtension('WEBGL_lose_context')?.loseContext()
    },
  }
}
