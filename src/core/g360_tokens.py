"""G360 Design Tokens.

Generado por `g360 tokens` â€” no editar a mano.
Snapshot estatico: tras cambiar la familia de acento, regenerar con
`g360 tokens --project <ruta>`.

Los roles son los mismos que en CSS, Go y Rust, para que los componentes
sean simetricos entre stacks.
"""

SKILL = "minimalista"
ACCENT_FAMILY = "blue"

TOKENS = {
    "dark": {
    "bg": "#0b1220",
    "surface": "#151e2e",
    "surfaceAlt": "#1c2941",
    "overlay": "rgba(11, 18, 32, 0.90)",
    "border": "rgba(255, 255, 255, 0.10)",
    "borderStrong": "rgba(255, 255, 255, 0.18)",
    "text": "#f0f4f8",
    "textMuted": "#94a3b8",
    "textInverse": "#0b1220",
    "accent": "#2563eb",
    "accentStrong": "#1d4ed8",
    "accentBright": "#60a5fa",
    "accentSoft": "rgba(37, 99, 235, 0.12)",
    "accentHover": "#60a5fa",
    "onAccent": "#ffffff",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "info": "#3b82f6",
    "glass": "rgba(21, 30, 46, 0.75)",
    "blur": "0px",
    "radius": "8px",
    "radiusSm": "8px",
    "font": "system-ui, -apple-system, 'Segoe UI', sans-serif",
    "fontMono": "'JetBrains Mono', 'Consolas', monospace",
    "fontSize": "14px",
    "spaceXs": "4px",
    "spaceSm": "8px",
    "spaceMd": "16px",
    "spaceLg": "24px",
    "spaceXl": "32px",
    },
    "light": {
    "bg": "#ffffff",
    "surface": "#f5f5f5",
    "surfaceAlt": "#eef2f7",
    "overlay": "rgba(255, 255, 255, 0.92)",
    "border": "rgba(0, 0, 0, 0.10)",
    "borderStrong": "rgba(0, 0, 0, 0.18)",
    "text": "#1f2937",
    "textMuted": "#6b7280",
    "textInverse": "#ffffff",
    "accent": "#2563eb",
    "accentStrong": "#2563eb",
    "accentBright": "#2563eb",
    "accentSoft": "rgba(37, 99, 235, 0.12)",
    "accentHover": "#2563eb",
    "onAccent": "#ffffff",
    "success": "#15803d",
    "warning": "#b45309",
    "error": "#dc2626",
    "info": "#0369a1",
    "glass": "rgba(255, 255, 255, 0.75)",
    "blur": "16px",
    "radius": "16px",
    "radiusSm": "8px",
    "font": "system-ui, -apple-system, 'Segoe UI', sans-serif",
    "fontMono": "'JetBrains Mono', 'Consolas', monospace",
    "fontSize": "14px",
    "spaceXs": "4px",
    "spaceSm": "8px",
    "spaceMd": "16px",
    "spaceLg": "24px",
    "spaceXl": "32px",
    },
    "chart": {
        "dark": ["#06b6d4", "#8b5cf6", "#0ea5e9", "#6366f1", "#ec4899", "#f59e0b", "#ef4444", "#f97316"],
        "light": ["#0891b2", "#7c3aed", "#0284c7", "#4f46e5", "#db2777", "#b45309", "#dc2626", "#ea580c"],
    },
}
