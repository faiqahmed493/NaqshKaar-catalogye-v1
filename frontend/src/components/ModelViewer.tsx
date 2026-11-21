// Three.js preview of a processed GLB. The magenta box is the recorded W × D × H, so the
// reviewer can see at a glance whether the mesh fills the product's real dimensions.
import { Bounds, Edges, Grid, Html, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { Component, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import * as THREE from "three";

interface Target { width: number | null; depth: number | null; height: number | null }

function Model({ url, onExtents }: { url: string; onExtents: (e: THREE.Vector3) => void }) {
  const { scene } = useGLTF(url);
  const copy = useMemo(() => scene.clone(true), [scene]);
  useEffect(() => {
    const size = new THREE.Box3().setFromObject(copy).getSize(new THREE.Vector3());
    onExtents(size);
  }, [copy, onExtents]);
  return <primitive object={copy} />;
}

function DimensionBox({ t }: { t: Target }) {
  if (!t.width || !t.depth || !t.height) return null;
  return (
    <group>
      <mesh position={[0, t.height / 2, 0]}>
        <boxGeometry args={[t.width, t.height, t.depth]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        <Edges color="#c2185b" />
      </mesh>
      <Html position={[0, 0.01, t.depth / 2 + 0.08]} center style={{ pointerEvents: "none" }}>
        <span className="chip" style={{ color: "#c2185b", background: "rgba(255,255,255,.9)" }}>front</span>
      </Html>
    </group>
  );
}

function Capture({ onCapture, delayMs = 900 }: { onCapture?: (blob: Blob) => void; delayMs?: number }) {
  const gl = useThree((s) => s.gl);
  useEffect(() => {
    if (!onCapture) return;
    const t = setTimeout(() => gl.domElement.toBlob((b) => b && onCapture(b), "image/png"), delayMs);
    return () => clearTimeout(t);
  }, [gl, onCapture, delayMs]);
  return null;
}

class ViewerBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) { return { error: e.message }; }
  render() {
    if (this.state.error) return <div className="empty"><div><b>Could not load this model</b><div className="small">{this.state.error}</div></div></div>;
    return this.props.children;
  }
}

export default function ModelViewer({ url, target, onCapture }: { url: string | null; target?: Target; onCapture?: (b: Blob) => void }) {
  const [ext, setExt] = useState<THREE.Vector3 | null>(null);
  const [grid, setGrid] = useState(true);
  useEffect(() => setExt(null), [url]);
  if (!url) return <div className="viewer"><div className="empty">No processed model yet.</div></div>;
  const f = (n: number) => `${(n * 100).toFixed(1)}`;
  return (
    <div className="viewer">
      <ViewerBoundary key={url}>
        <Canvas camera={{ position: [2.2, 1.6, 2.6], fov: 38 }} gl={{ preserveDrawingBuffer: true, antialias: true }} dpr={[1, 2]}>
          <color attach="background" args={["#eef2f3"]} />
          <hemisphereLight args={["#ffffff", "#b9c4c9", 1.1]} />
          <directionalLight position={[3, 5, 4]} intensity={1.6} />
          <directionalLight position={[-4, 2, -3]} intensity={0.5} />
          <Suspense fallback={<Html center><span className="chip">Loading model…</span></Html>}>
            <Bounds fit clip observe margin={1.25}>
              <Model url={url} onExtents={setExt} />
              {target && <DimensionBox t={target} />}
            </Bounds>
            <Capture onCapture={onCapture} />
          </Suspense>
          {grid && <Grid infiniteGrid cellSize={0.1} sectionSize={1} cellColor="#cfd8dc" sectionColor="#9fb0b8" fadeDistance={12} />}
          <OrbitControls makeDefault enableDamping />
        </Canvas>
      </ViewerBoundary>
      <div className="overlay">
        {ext && <span className="chip">Mesh {f(ext.x)} × {f(ext.z)} × {f(ext.y)} cm (W × D × H)</span>}
        {target?.width && <span className="chip dimchip">Recorded {f(target.width)} × {f(target.depth ?? 0)} × {f(target.height ?? 0)} cm</span>}
      </div>
      <div className="tools">
        <button className="btn small" onClick={() => setGrid((g) => !g)}>{grid ? "Hide grid" : "Show grid"}</button>
      </div>
    </div>
  );
}
