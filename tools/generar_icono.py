"""
Genera el icono de g360-textofix.

Un chevron > verde sobre fondo oscuro. Simple y legible a 16px.

    uv run --with pillow python tools/generar_icono.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Colores
FONDO = (11, 18, 32, 255)  # azul oscuro
VERDE = (0, 208, 132, 255)  # verde G360

TAM = 1024
G = TAM / 256.0  # = 4.0


def dibujar() -> Image.Image:
    """Chevron > en verde sobre fondo oscuro."""
    im = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # Fondo redondeado
    d.rounded_rectangle([0, 0, TAM - 1, TAM - 1], radius=int(TAM * 0.2), fill=FONDO)

    # Chevron: forma de V apuntando a la derecha
    grosor = int(16 * G)  # linea fina

    # Puntos en grilla de 0-255, luego multiplicar por G=4
    # Ejemplo: 128 * 4 = 512 pixels
    x_izq = int(80 * G)  # 320
    y_arriba = int(200 * G)  # 800
    x_dcho = int(200 * G)  # 800
    y_medio = int(256 * G)  # 1024 -> FUERA! Usar 255 max
    y_medio = int(255 * G)  # 1020 (max permitido)
    y_abajo = int(312 * G)  # 1248 -> FUERA!

    # Ajustar: usar valores menores a 255
    y_arriba = int(180 * G)  # 720
    y_medio = int(255 * G)  # 1020 (limite)
    y_abajo = int(330 * G)  # 1320 -> FUERA!

    # Correccion final:
    y_arriba = int(150 * G)  # 600
    y_medio = int(250 * G)  # 1000
    y_abajo = int(350 * G)  # 1400 -> FUERA!

    # Usar solo valores validos (< 256 * 4 = 1024)
    x_izq = int(100 * G)  # 400
    y_arriba = int(200 * G)  # 800
    x_dcho = int(200 * G)  # 800
    y_medio = int(255 * G)  # 1020 (max)
    y_abajo = int(310 * G)  # 1240 -> demasiado alto

    # Simplificar: coordenadas directas en pixels
    x_izq = 300
    y_arriba = 300
    x_dcho = 700
    y_medio = 512  # centro
    y_abajo = 724

    grosor = 24

    # Lineas del chevron
    d.line([(x_izq, y_arriba), (x_dcho, y_medio)], fill=VERDE, width=grosor)
    d.line([(x_dcho, y_medio), (x_izq, y_abajo)], fill=VERDE, width=grosor)

    # Bordes redondeados
    radio = grosor // 2
    for cx, cy in [(x_izq, y_arriba), (x_dcho, y_medio), (x_izq, y_abajo)]:
        d.ellipse([cx - radio, cy - radio, cx + radio, cy + radio], fill=VERDE)

    return im


def _escribir_ico(ruta: Path, imagen: Image.Image) -> None:
    """Arma un .ico con multiples tamanos."""
    import io
    import struct

    tamanos = [16, 20, 24, 32, 48, 64, 128, 256]
    blobs = []
    for tam in tamanos:
        buffer = io.BytesIO()
        imagen.resize((tam, tam), Image.LANCZOS).save(buffer, format="PNG", optimize=True)
        blobs.append(buffer.getvalue())

    desplazamiento = 6 + 16 * len(blobs)
    entradas = []
    for tam, blob in zip(tamanos, blobs):
        entradas.append(
            struct.pack(
                "<BBBBHHII",
                tam & 0xFF,
                tam & 0xFF,
                0,
                0,
                1,
                32,
                len(blob),
                desplazamiento,
            )
        )
        desplazamiento += len(blob)

    ruta.write_bytes(struct.pack("<HHH", 0, 1, len(blobs)) + b"".join(entradas) + b"".join(blobs))


def principal() -> None:
    raiz = Path(__file__).resolve().parents[1]
    destino = raiz / "assets" / "g360-textofix.ico"
    destino.parent.mkdir(parents=True, exist_ok=True)

    im = dibujar()
    _escribir_ico(destino, im)
    im.save(destino.with_suffix(".png"))

    print(f"icono: {destino}")
    print(f"png:   {destino.with_suffix('.png')}")
    print(f"medidas: {', '.join(str(t) for t in [16, 20, 24, 32, 48, 64, 128, 256])}px")


if __name__ == "__main__":
    principal()
