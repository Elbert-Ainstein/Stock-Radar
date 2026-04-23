import { useRef, useEffect, useCallback } from "react";
import * as THREE from "three";
import type { GlobeCandidate } from "./geo-data";

export const GLOBE_RADIUS = 1.2;

interface GlobeSceneRefs {
  containerRef: React.RefObject<HTMLDivElement | null>;
  rendererRef: React.MutableRefObject<THREE.WebGLRenderer | null>;
  sceneRef: React.MutableRefObject<THREE.Scene | null>;
  cameraRef: React.MutableRefObject<THREE.PerspectiveCamera | null>;
  globeRef: React.MutableRefObject<THREE.Mesh | null>;
  pinsGroupRef: React.MutableRefObject<THREE.Group | null>;
  raycasterRef: React.MutableRefObject<THREE.Raycaster>;
  mouseRef: React.MutableRefObject<THREE.Vector2>;
  animFrameRef: React.MutableRefObject<number>;
  isDraggingRef: React.MutableRefObject<boolean>;
  prevMouseRef: React.MutableRefObject<{ x: number; y: number }>;
  rotationRef: React.MutableRefObject<{ x: number; y: number }>;
  autoRotateRef: React.MutableRefObject<boolean>;
  hoverPinRef: React.MutableRefObject<THREE.Mesh | null>;
}

export function useGlobeRefs(): GlobeSceneRefs {
  return {
    containerRef: useRef<HTMLDivElement | null>(null),
    rendererRef: useRef<THREE.WebGLRenderer | null>(null),
    sceneRef: useRef<THREE.Scene | null>(null),
    cameraRef: useRef<THREE.PerspectiveCamera | null>(null),
    globeRef: useRef<THREE.Mesh | null>(null),
    pinsGroupRef: useRef<THREE.Group | null>(null),
    raycasterRef: useRef(new THREE.Raycaster()),
    mouseRef: useRef(new THREE.Vector2()),
    animFrameRef: useRef<number>(0),
    isDraggingRef: useRef(false),
    prevMouseRef: useRef({ x: 0, y: 0 }),
    rotationRef: useRef({ x: 0.3, y: -0.5 }),
    autoRotateRef: useRef(true),
    hoverPinRef: useRef<THREE.Mesh | null>(null),
  };
}

export function useGlobeScene(
  refs: GlobeSceneRefs,
  callbacks: {
    onHover: (data: { candidate: GlobeCandidate; x: number; y: number } | null) => void;
    onSelect: (candidate: GlobeCandidate) => void;
  }
) {
  const {
    containerRef,
    rendererRef,
    sceneRef,
    cameraRef,
    globeRef,
    pinsGroupRef,
    raycasterRef,
    mouseRef,
    animFrameRef,
    isDraggingRef,
    prevMouseRef,
    rotationRef,
    autoRotateRef,
    hoverPinRef,
  } = refs;

  const { onHover, onSelect } = callbacks;

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 3.5;
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // ─── Globe geometry ───
    const globeGeom = new THREE.SphereGeometry(GLOBE_RADIUS, 64, 64);

    const globeMat = new THREE.MeshPhongMaterial({
      color: 0x1a1a2e,
      emissive: 0x0a0a15,
      specular: 0x333355,
      shininess: 15,
      transparent: true,
      opacity: 0.92,
    });

    const globe = new THREE.Mesh(globeGeom, globeMat);
    scene.add(globe);
    globeRef.current = globe;

    // Atmosphere glow
    const atmosGeom = new THREE.SphereGeometry(GLOBE_RADIUS * 1.02, 64, 64);
    const atmosMat = new THREE.MeshBasicMaterial({
      color: 0x4488ff,
      transparent: true,
      opacity: 0.08,
      side: THREE.BackSide,
    });
    const atmos = new THREE.Mesh(atmosGeom, atmosMat);
    scene.add(atmos);

    // Outer glow
    const outerGlowGeom = new THREE.SphereGeometry(GLOBE_RADIUS * 1.15, 32, 32);
    const outerGlowMat = new THREE.MeshBasicMaterial({
      color: 0x2244aa,
      transparent: true,
      opacity: 0.04,
      side: THREE.BackSide,
    });
    scene.add(new THREE.Mesh(outerGlowGeom, outerGlowMat));

    // Wireframe grid
    const wireGeom = new THREE.SphereGeometry(GLOBE_RADIUS * 1.001, 36, 18);
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0x334466,
      wireframe: true,
      transparent: true,
      opacity: 0.15,
    });
    scene.add(new THREE.Mesh(wireGeom, wireMat));

    // Lighting
    const ambient = new THREE.AmbientLight(0x334466, 0.6);
    scene.add(ambient);

    const directional = new THREE.DirectionalLight(0xffffff, 0.8);
    directional.position.set(5, 3, 5);
    scene.add(directional);

    const pointLight = new THREE.PointLight(0x4488ff, 0.4, 10);
    pointLight.position.set(-3, 2, -3);
    scene.add(pointLight);

    // Pins group
    const pinsGroup = new THREE.Group();
    scene.add(pinsGroup);
    pinsGroupRef.current = pinsGroup;

    // ─── Animate ───
    const animate = () => {
      animFrameRef.current = requestAnimationFrame(animate);

      if (autoRotateRef.current && !isDraggingRef.current) {
        rotationRef.current.y += 0.002;
      }

      globe.rotation.x = rotationRef.current.x;
      globe.rotation.y = rotationRef.current.y;
      atmos.rotation.x = rotationRef.current.x;
      atmos.rotation.y = rotationRef.current.y;
      pinsGroup.rotation.x = rotationRef.current.x;
      pinsGroup.rotation.y = rotationRef.current.y;

      // Pulse pins
      pinsGroup.children.forEach((child) => {
        if (child instanceof THREE.Mesh && child.userData.isPulse) {
          const scale = 1 + 0.3 * Math.sin(Date.now() * 0.003 + child.userData.phase);
          child.scale.set(scale, scale, scale);
          (child.material as THREE.MeshBasicMaterial).opacity =
            0.3 + 0.15 * Math.sin(Date.now() * 0.003 + child.userData.phase);
        }
      });

      renderer.render(scene, camera);
    };
    animate();

    // ─── Resize handler ───
    const onResize = () => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    // ─── Mouse interaction ───
    const onMouseDown = (e: MouseEvent) => {
      isDraggingRef.current = true;
      autoRotateRef.current = false;
      prevMouseRef.current = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      mouseRef.current.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouseRef.current.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      if (isDraggingRef.current) {
        const dx = e.clientX - prevMouseRef.current.x;
        const dy = e.clientY - prevMouseRef.current.y;
        rotationRef.current.y += dx * 0.005;
        rotationRef.current.x += dy * 0.005;
        rotationRef.current.x = Math.max(
          -Math.PI / 2,
          Math.min(Math.PI / 2, rotationRef.current.x)
        );
        prevMouseRef.current = { x: e.clientX, y: e.clientY };
      } else {
        // Hover detection
        raycasterRef.current.setFromCamera(mouseRef.current, camera);
        const pinMeshes = pinsGroup.children.filter(
          (c) => c instanceof THREE.Mesh && c.userData.isPin
        );
        const intersects = raycasterRef.current.intersectObjects(pinMeshes);

        if (intersects.length > 0) {
          const pin = intersects[0].object as THREE.Mesh;
          container.style.cursor = "pointer";

          if (hoverPinRef.current !== pin) {
            if (hoverPinRef.current) {
              (hoverPinRef.current.material as THREE.MeshBasicMaterial).opacity = 0.95;
            }
            (pin.material as THREE.MeshBasicMaterial).opacity = 1.0;
            hoverPinRef.current = pin;
          }

          onHover({
            candidate: pin.userData.candidate,
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
          });
        } else {
          container.style.cursor = "grab";
          hoverPinRef.current = null;
          onHover(null);
        }
      }
    };

    const onMouseUp = () => {
      if (isDraggingRef.current) {
        isDraggingRef.current = false;
        setTimeout(() => {
          if (!isDraggingRef.current) autoRotateRef.current = true;
        }, 3000);
      }
    };

    const onClick = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const mouse = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1
      );
      raycasterRef.current.setFromCamera(mouse, camera);
      const pinMeshes = pinsGroup.children.filter(
        (c) => c instanceof THREE.Mesh && c.userData.isPin
      );
      const intersects = raycasterRef.current.intersectObjects(pinMeshes);
      if (intersects.length > 0) {
        const pin = intersects[0].object as THREE.Mesh;
        onSelect(pin.userData.candidate);
        onHover(null);
      }
    };

    container.addEventListener("mousedown", onMouseDown);
    container.addEventListener("mousemove", onMouseMove);
    container.addEventListener("mouseup", onMouseUp);
    container.addEventListener("mouseleave", onMouseUp);
    container.addEventListener("click", onClick);

    // Touch support
    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 1) {
        isDraggingRef.current = true;
        autoRotateRef.current = false;
        prevMouseRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    };
    const onTouchMove = (e: TouchEvent) => {
      if (isDraggingRef.current && e.touches.length === 1) {
        const dx = e.touches[0].clientX - prevMouseRef.current.x;
        const dy = e.touches[0].clientY - prevMouseRef.current.y;
        rotationRef.current.y += dx * 0.005;
        rotationRef.current.x += dy * 0.005;
        rotationRef.current.x = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, rotationRef.current.x));
        prevMouseRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    };
    const onTouchEnd = () => {
      isDraggingRef.current = false;
      setTimeout(() => {
        if (!isDraggingRef.current) autoRotateRef.current = true;
      }, 3000);
    };

    container.addEventListener("touchstart", onTouchStart, { passive: true });
    container.addEventListener("touchmove", onTouchMove, { passive: true });
    container.addEventListener("touchend", onTouchEnd);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener("resize", onResize);
      container.removeEventListener("mousedown", onMouseDown);
      container.removeEventListener("mousemove", onMouseMove);
      container.removeEventListener("mouseup", onMouseUp);
      container.removeEventListener("mouseleave", onMouseUp);
      container.removeEventListener("click", onClick);
      container.removeEventListener("touchstart", onTouchStart);
      container.removeEventListener("touchmove", onTouchMove);
      container.removeEventListener("touchend", onTouchEnd);
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry?.dispose();
          if (obj.material instanceof THREE.Material) {
            obj.material.dispose();
          } else if (Array.isArray(obj.material)) {
            obj.material.forEach((m: THREE.Material) => m.dispose());
          }
        }
      });
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
