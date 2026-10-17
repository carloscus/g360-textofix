# g360-textofix

> Corrector de texto para Windows: atajo global, captura de la selección y reemplazo en el lugar.

Microherramienta del ecosistema G360. Seleccionás un texto en cualquier
aplicación, apretás `Ctrl+Shift+E` y el texto seleccionado se corrige y se
reemplaza donde estaba, sin perder el formato.

**Estado: Etapa 1 terminada.** El ciclo completo funciona (captura, validación,
reemplazo) pero todavía **no corrige con IA**: hoy usa un sustituto simulado
para poder validar la mecánica. La corrección con Gemini es la Etapa 2 y está
pendiente de configurar la facturación.

---

## Tabla de contenidos

- [Cómo usar](#cómo-usar)
- [Qué funciona hoy](#qué-funciona-hoy)
- [Instalación](#instalación)
- [Comandos](#comandos)
- [Configuración](#configuración)
- [Cómo decide a quién corregir](#cómo-decide-a-quién-corregir)
- [Garantías de seguridad](#garantías-de-seguridad)
- [Etapa 2: corrección con Gemini](#etapa-2-corrección-con-gemini)
- [Estructura](#estructura)
- [Testing](#testing)
- [Licencia](#licencia)

---

## Cómo usar

1. Abrí la aplicación donde quieras corregir (Bloc de notas, Word, Excel, navegador, correo).
2. Seleccioná el texto con el ratón o el teclado.
3. Apretá `Ctrl + Shift + E`.

| Situación | Qué pasa |
|---|---|
| Hay texto seleccionado y se corrige | Se reemplaza en el lugar. Tono agudo. |
| El texto ya estaba bien | No se toca nada. Tono agudo. |
| No hay nada seleccionado | No se toca nada. Tono medio. |
| Algo falla (red, respuesta inválida, app protegida) | El original queda intacto. Tono grave. |

---

## Qué funciona hoy

Verificado con pruebas de humo automatizadas contra aplicaciones reales en esta
máquina. Cada línea corresponde a un `tests/smoke_*.py` que se puede volver a
ejecutar.

| Aplicación | Captura | Reemplazo | Notas |
|---|---|---|---|
| Control EDIT de Win32 | ✅ | ✅ | Selección completa, parcial, al final y sin selección |
| Bloc de notas (Windows 11) | ✅ | ✅ | Solo expone `ValuePattern`, va por portapapeles |
| Chrome: `<textarea>` | ✅ | ✅ | Lee por `TextPattern`, sin pasar por portapapeles |
| Chrome: `contenteditable` | ✅ | ✅ | Ídem |
| Word | ✅ COM | ✅ | Conserva párrafos y formato; no duplica párrafos |
| Excel | ✅ COM | ✅ | Solo celdas de texto; fórmulas y números intactos |

### Lo que NO está verificado

Se dice explícitamente para no dar por bueno lo que no se probó:

| Sin verificar | Por qué |
|---|---|
| **Outlook / correo** | La prueba automatizada escribiría en tu buzón real. La ruta técnica es la misma que el navegador (UIA → portapapeles), pero **no está confirmada**. Probalo a mano antes de confiar en él. |
| **ERP (Centura)** | No se automatizó por riesgo de tocar datos reales de negocio. Además suele **correrse como administrador**: si es el caso, el corrector detecta el bloqueo (UIPI) y avisa con tono grave, pero no puede corregirlo. Habría que lanzarlo elevated. |
| **Other navegadores** | Solo Chrome. Brave, Firefox y Edge comparten tecnología pero no se probaron. |
| **Consolas / terminal** | Sin verificar. |
| **WordPad, apps con diseño propio** | Sin verificar. |
| **Aplicaciones con contraseña o campos restringidos** | Sin verificar. |
| **Escritorio remoto** | Sin verificar. |

**Prueba rápida:** `uv run python src/main.py --diagnostico` dice qué ventana ve el
corrector, qué adaptador usaría y si está bloqueado por permisos.

---

## Instalación

Requiere Windows y [uv](https://github.com/astral-sh/uv) (se encarga solo del
entorno y las dependencias).

```bat
:: 1. Instalar uv y dependencias
setup.bat

:: 2. Arrancar el corrector
iniciar.bat
```

Alternativa sin `.bat`:

```powershell
uv sync
uv run python src/main.py
```

> **Nota sobre Python**: el proyecto no depende del Python del sistema. `uv`
> crea su propio entorno. Los lanzadores `py` y `pytest` del sistema apuntan a
> un Python 3.14 que no está instalado; por eso todo pasa por `uv run`.

---

## Comandos

| Comando | Qué hace |
|---|---|
| `uv run python src/main.py` | Escucha el atajo `Ctrl+Shift+E` |
| `uv run python src/main.py --once` | Una corrección sobre lo seleccionado y sale |
| `uv run python src/main.py --once --mock-transform wrap` | Envuelve el texto en `«»` para ver dónde se escribió |
| `uv run python src/main.py --diagnostico` | Informa qué ventana está en primer plano y qué adaptador usaría |
| `uv run python src/main.py -v` | Detalle en consola |

`--diagnostico` es el primer comando para usar si algo falla: dice si la
aplicación está bloqueada (UIPI) y qué adaptador corresponde.

---

## Configuración

Copiá `.env.example` a `.env` y ajustá lo que necesites. Todos los valores son
opcionales.

| Variable | Por defecto | Para qué |
|---|---|---|
| `TEXTOFIX_SOUND` | `true` | Desactiva los tonos (pruebas automatizadas) |
| `TEXTOFIX_ENABLED` | `true` | Desactiva el corrector sin salir |
| `TEXTOFIX_VERBOSE` | `false` | Detalle en consola |
| `TEXTOFIX_CLIPBOARD_TIMEOUT_MS` | `400` | Espera al `Ctrl+C`. Subirlo ayuda en equipos lentos |

---

## Cómo decide a quién corregir

No hay una única estrategia: cada aplicación expone la selección de forma
distinta. Los adaptadores se consultan en orden de prioridad.

```
                    ┌─ winword.exe  → COM, lee Selection.Range
Atajo ──→ detectar ─┼─ excel.exe    → COM, lee ActiveCell
                    └─ resto        → UIA (TextPattern) → portapapeles
```

| Adaptador | Cuándo | Cómo lee |
|---|---|---|
| `word` | `winword.exe` | COM `Selection.Range` |
| `excel` | `excel.exe` | COM `ActiveCell` |
| `generic` | todo lo demás | UIA y, si no alcanza, portapapeles |

**Por qué el portapapeles sigue en el camino genérico.** UI Automation tiene
dos patrones y no sirven para lo mismo:

- `TextPattern.GetSelection()` devuelve el texto **realmente resaltado**.
- `ValuePattern` devuelve el valor **completo** del control.

El Bloc de notas de Windows 11 expone `ValuePattern` y **no** `TextPattern`.
Leer con `ValuePattern` y reescribir con `SetValue()` borraría todo lo que el
usuario no había seleccionado. Por eso, cuando UIA no expone la selección, se
va al portapapeles: el pegado sí respeta lo resaltado.

---

## Garantías de seguridad

El principio es uno: **ante cualquier duda, no se escribe nada**.

**Las guardas** (`src/core/guards.py`, módulo puro con tests) rechazan la
respuesta si:

| Guarda | Qué evita |
|---|---|
| Respuesta vacía | Borrar la selección |
| Bloque de código o preámbulo ("Aquí tienes…") | Pegar basura en el documento |
| La respuesta crece >2× o cae <30% | Parafrasear en vez de corregir |
| **Las cifras cambian** | Que el modelo invente o altere montos, fechas o códigos |
| El texto no cambió | Pisar el formato sin necesidad |

**Las guardas de Office**:

- Excel: una celda con **fórmula nunca se toca**; los valores numéricos tampoco
  (un corrector ortográfico no corrige números).
- Excel: se revalida la celda justo antes de escribir, por si el usuario movió
  la selección.
- Excel: hoja protegida → no se escribe.
- Word: nunca se reemplaza la marca de párrafo final, así que no se crean
  párrafos de más.

**Privacidad**:

- **No hay historial**: no se guarda ninguna corrección.
- **Los logs no contienen texto**: solo longitud y un hash (`len=42 sha=3f9a1c2b`).
- **El portapapeles se restaura siempre**, haya escrito o no. Leer la selección de
  muchas apps exige copiarla, así que si la corrección se rechaza el portapapeles
  del usuario también queda como estaba.
- **No se crea ningún archivo de log**: todo va a consola.

---

## Etapa 2: corrección con Gemini

Pendiente. Requiere dos cosas:

1. **Facturación activada** en el proyecto de Google AI Studio.
2. La clave en `GEMINI_API_KEY` dentro de `.env`.

> **Por qué hace falta la facturación.** Los
> [términos de Gemini API](https://ai.google.dev/gemini-api/terms) dicen que en
> la cuota **gratuita** Google usa los textos enviados para mejorar sus
> productos y que **revisores humanos pueden leerlos**. En la cuota **de pago**
> no se usan para entrenar. Como el corrector se usa sobre correo, documentos y
> sistemas empresariales, corresponde la cuota de pago.

---

## Estructura

```text
g360-textofix/
├── pyproject.toml              # dependencias (uv)
├── iniciar.bat                 # lanzador
├── setup.bat                   # instala uv y dependencias
├── .env.example                # plantilla de configuración
├── src/
│   ├── main.py                 # CLI y bucle del atajo
│   └── core/
│       ├── config.py           # configuración por entorno
│       ├── hotkey.py           # RegisterHotKey (sin admin)
│       ├── engine.py           # ciclo: leer -> corregir -> validar -> escribir
│       ├── guards.py           # validaciones (puro, sin Windows)
│       ├── winapi.py           # Win32, SendInput, portapapeles, UIPI
│       ├── feedback.py         # tonos (winsound, stdlib)
│       ├── logsetup.py         # logging sin contenido
│       └── adapters/
│           ├── base.py         # contrato
│           ├── word.py         # Word por COM
│           ├── excel.py        # Excel por COM
│           └── generic.py      # UIA + portapapeles
└── tests/
    ├── test_guards.py          # tests de las guardas (puros)
    ├── test_frases.py          # batería de frases (§5 del plan)
    └── smoke_*.py              # pruebas de humo reales
```

---

## Testing

```powershell
:: Tests unitarios (rápidos, sin Windows)
uv run pytest

:: Pruebas de humo (abren ventanas reales y escriben en apps de verdad)
uv run python tests/smoke_win32_edit.py    # selección completa, parcial, al final, sin selección
uv run python tests/smoke_hotkey.py        # atajo global, sin ráfaga, cierre limpio
uv run python tests/smoke_privacidad.py    # logs sin texto, portapapeles intacto
uv run python tests/smoke_notepad.py       # Bloc de notas
uv run python tests/smoke_navegador.py     # Chrome: textarea y contenteditable
uv run python tests/smoke_office.py        # Word y Excel
```

Las pruebas de humo no las corre `pytest`: abren ventanas y escriben en
aplicaciones de verdad, así que se lanzan a mano. Todas terminan con `exit 0` si
pasan.

`smoke_navegador.py` abre Chrome con un perfil aislado en una carpeta temporal, así
que no toca tu perfil real ni otros navegadores abiertos.

---

## Licencia

MIT.

---

## Familia G360

Microherramienta del [ecosistema G360](https://github.com/carloscus), una
familia de herramientas de apoyo CRM y gestión de datos en escritorio.