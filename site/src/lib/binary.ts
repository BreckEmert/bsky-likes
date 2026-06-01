// Loader for the Theo-format binary point lookups shared by svg-point and
// deck.gl plots:
//   handles.bin  : uint32 count, (count+1) uint32 offsets, then UTF-8 bytes
//   positions.bin: Float32Array [x0,y0,x1,y1,...] parallel to handles
//
// One format for every searchable point plot (typical-popularity, like-repost,
// activity, punching) — no giant JSON to parse on the client.

export interface PointData {
  handles: string[];                 // lowercased, index i <-> positions[2i]
  positions: Float32Array;           // [x0,y0,x1,y1,...] in data units
  index: Map<string, number>;        // handle -> i
  get(handle: string): [number, number] | undefined;
}

function parseHandles(buf: ArrayBuffer): string[] {
  const dv = new DataView(buf);
  const count = dv.getUint32(0, true);
  const offsets = new Uint32Array(buf, 4, count + 1);
  const bytesStart = 4 + (count + 1) * 4;
  const u8 = new Uint8Array(buf);
  const dec = new TextDecoder();
  const handles = new Array<string>(count);
  for (let i = 0; i < count; i++) {
    handles[i] = dec.decode(u8.subarray(bytesStart + offsets[i], bytesStart + offsets[i + 1]));
  }
  return handles;
}

export async function loadPointData(
  handlesUrl: string,
  positionsUrl: string
): Promise<PointData> {
  const [hb, pb] = await Promise.all([
    fetch(handlesUrl).then((r) => r.arrayBuffer()),
    fetch(positionsUrl).then((r) => r.arrayBuffer()),
  ]);
  const handles = parseHandles(hb);
  const positions = new Float32Array(pb);
  const index = new Map<string, number>();
  for (let i = 0; i < handles.length; i++) index.set(handles[i], i);
  return {
    handles,
    positions,
    index,
    get(handle: string) {
      const i = index.get(handle.toLowerCase());
      return i === undefined ? undefined : [positions[2 * i], positions[2 * i + 1]];
    },
  };
}
