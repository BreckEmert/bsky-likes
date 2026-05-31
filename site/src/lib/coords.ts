// Coordinate mapping between a plot's DATA space and on-screen PIXELS.
//
// The matplotlib PNG is the chart. We only ever draw a highlight (ring/dot/
// line) on top of it, so the single job here is: given a user's (x, y) in data
// units, find the pixel over the displayed (letterboxed) image.
//
// Pipeline (per axis):
//   data value
//     -> log10 if that axis is log-scaled
//     -> fraction across [min, max]
//     -> PNG pixel inside `plotArea` (the axes rectangle within the PNG)
//     -> displayed pixel inside the letterboxed image rect on screen
//
// Image Y is top-down, but data Y is bottom-up, so the Y mapping is flipped.

/** Shape of `<plot>.bounds.json` emitted by bsky_export_web.py. */
export interface Bounds {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  xLog: boolean;
  yLog: boolean;
  imgWidth: number;
  imgHeight: number;
  /** Pixel rectangle of the axes (data area) inside the PNG. top < bottom. */
  plotArea: { left: number; top: number; right: number; bottom: number };
}

/** A rectangle in container pixels (left/top origin). */
export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

function maybeLog(v: number, isLog: boolean): number {
  return isLog ? Math.log10(v) : v;
}

/**
 * The rectangle an `object-fit: contain` image occupies inside a box of
 * (boxW x boxH), preserving the image's natural aspect ratio and centering it.
 * This must match the CSS letterboxing exactly so overlays line up.
 */
export function containRect(
  boxW: number,
  boxH: number,
  natW: number,
  natH: number
): Rect {
  if (boxW <= 0 || boxH <= 0 || natW <= 0 || natH <= 0) {
    return { left: 0, top: 0, width: 0, height: 0 };
  }
  const scale = Math.min(boxW / natW, boxH / natH);
  const width = natW * scale;
  const height = natH * scale;
  return { left: (boxW - width) / 2, top: (boxH - height) / 2, width, height };
}

/**
 * Map a data-space (x, y) to a pixel within the displayed image rect.
 * `imgRect` is where the PNG is actually drawn on screen (from containRect).
 */
export function dataToPixel(
  b: Bounds,
  imgRect: Rect,
  x: number,
  y: number
): Point {
  const lx = maybeLog(x, b.xLog);
  const ly = maybeLog(y, b.yLog);
  const lxMin = maybeLog(b.xMin, b.xLog);
  const lxMax = maybeLog(b.xMax, b.xLog);
  const lyMin = maybeLog(b.yMin, b.yLog);
  const lyMax = maybeLog(b.yMax, b.yLog);

  const fx = (lx - lxMin) / (lxMax - lxMin); // 0 at left, 1 at right
  const fy = (ly - lyMin) / (lyMax - lyMin); // 0 at bottom, 1 at top

  // Fraction -> PNG pixel inside the axes rect (Y flipped: top is small pixel).
  const pngX = b.plotArea.left + fx * (b.plotArea.right - b.plotArea.left);
  const pngY = b.plotArea.bottom - fy * (b.plotArea.bottom - b.plotArea.top);

  // PNG pixel -> displayed pixel (scale by how big the image is drawn).
  return {
    x: imgRect.left + (pngX / b.imgWidth) * imgRect.width,
    y: imgRect.top + (pngY / b.imgHeight) * imgRect.height,
  };
}

/**
 * Whole-image, linear 0..1 bounds. Used as a fallback so overlay/letterbox
 * plumbing can be verified BEFORE the real bounds.json exports exist; with
 * these, data (0.5, 0.5) maps to the visual center of the image.
 */
export function identityBounds(imgWidth: number, imgHeight: number): Bounds {
  return {
    xMin: 0,
    xMax: 1,
    yMin: 0,
    yMax: 1,
    xLog: false,
    yLog: false,
    imgWidth,
    imgHeight,
    plotArea: { left: 0, top: 0, right: imgWidth, bottom: imgHeight },
  };
}
