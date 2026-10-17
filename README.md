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
| Ejecución desde un hilo de trabajo | ✅ | ✅ | Es el camino real del atajo global; exige COM inicializado por hilo |
| Bloc de notas (Windows 11) | ✅ | ✅ | Solo expone `ValuePattern`, va por portapapeles |
| Chrome: `<textarea>` | ✅ | ✅ | Lee por `TextPattern`, sin pasar por portapapeles |
| Chrome: `contenteditable` | ✅ | ✅ | Ídem |
| **Flet / Flutter (campos)** | ✅ | ✅ | Sin `TextPattern` y sin `Ctrl+C`: corrige el campo entero |
| **Outlook (redactar)** | ✅ UIA | ✅ | No acepta `Ctrl+V`: escribe a mano tras comprobarlo |
| **Outlook (bandeja)** | ✅ lectura | ❌ | El panel de lectura es **solo lectura**: no se puede pegar |
| Word | ✅ COM | ✅ | Conserva párrafos y formato; no duplica párrafos |
| Excel | ✅ COM | ✅ | Solo celdas de texto; fórmulas y números intactos |

### Lo que NO está verificado

Se dice explícitamente para no dar por bueno lo que no se probó:

| Sin verificar | Por qué |
|---|---|
| **Outlook / correo** | Verificado en la ventana de redacción. El panel de lectura de la bandeja es solo lectura: ahí no hay nada que corregir. |
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
| `uv run python src/main.py --modo ia` | Igual, pero **corrige de verdad** con Gemini |
| `uv run python src/main.py --once` | Una corrección sobre lo seleccionado y sale |
| `uv run python src/main.py --once --mock-transform wrap` | Envuelve el texto en `«»` para ver dónde se escribió |
| `uv run python src/main.py --bateria` | Mide el prompt contra la batería de frases, sin escribir nada |
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
                    └─ resto        → UIA → portapapeles → campo entero
```

| Adaptador | Cuándo | Cómo lee |
|---|---|---|
| `word` | `winword.exe` | COM `Selection.Range` |
| `excel` | `excel.exe` | COM `ActiveCell` |
| `generic` | todo lo demás | UIA → portapapeles → campo entero |

### El camino "campo entero" y cuándo se activa

UI Automation tiene dos patrones y no sirven para lo mismo:

- `TextPattern.GetSelection()` devuelve el texto **realmente resaltado**.
- `ValuePattern` devuelve el valor **completo** del control.

El Bloc de notas de Windows 11 expone `ValuePattern` y **no** `TextPattern`.
Leer con `ValuePattern` y reescribir con `SetValue()` borraría todo lo que el
usuario no había seleccionado.

Por eso el orden va de lo preciso a lo aproximado, y el valor completo queda
**solo como último recurso**, y únicamente si se cumplen **las dos** condiciones:

1. El control **no** expone `TextPattern`.
2. Esa aplicación **nunca** ha respondido a un `Ctrl+C` sintético.

La segunda condición existe por apps como **Flutter (Flet)**: dibujan el texto
ellos mismos, no exponen `TextPattern` y no responden al `Ctrl+C` sintético (ni
siquiera con un clic real). Ahí "no se copió nada" es ambiguo: puede ser que no
tengas nada seleccionado o que la app ni entienda el atajo. El corrector recuerda
qué apps han copiado alguna vez y solo usa este camino en las que nunca lo han
hecho.

**El precio, dicho claro:** en esas apps se corrige y se reescribe el **campo
entero**. No se pierde texto (todo el contenido se conserva y se corrige), pero
si habías seleccionado solo una parte, esa intención se ignora.

**En esos casos el log lo dice**: `sin seleccion detectable: se corrige el campo
entero (N caracteres)`.

### Flutter/Flet: escribir a mano

Flutter no es un control de Windows: dibuja el texto él mismo. Medido sobre una
app Flet real, casi nada de lo habitual funciona:

| Vía | Resultado |
|---|---|
| `TextPattern` (saber la selección) | No existe |
| `Ctrl+C` / `Ctrl+V` sintéticos | No hacen nada |
| `ValuePattern.SetValue()` | Falla siempre con "Unspecified error" |
| `Home` / `End` / triple clic | No seleccionan |
| **`Ctrl+End`** | **Sí funciona** |
| **Retroceso** | **Sí funciona** |
| **Escribir con `KEYEVENTF_UNICODE`** | **Sí funciona** |

Así que el campo se limpia con tantos Retrocesos como caracteres tenga (con
margen) y se vuelve a escribir. Los eventos van en un solo `SendInput`: enviados
de a uno, Flutter pierde algunos y el campo queda con restos.

Y **no se hace clic antes de escribir**: el usuario ya hizo clic en el campo
antes de apretar el atajo. Añadir un clic extra dejaba el cursor en medio del
texto y la escritura fallaba.

Los campos de **varias líneas se rechazan**: no hay forma de saber dónde termina
el texto y un borrado a ciegas sería peligroso.

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

**Antes de escribir, se revalida la selección** (idea tomada de
[GhostEdit](https://github.com/nareshnavinash/GhostEdit), que resuelve el mismo
problema):

1. Se vuelve a copiar lo seleccionado y se compara con lo que se iba a
   corregir. Si no coincide, no se escribe nada. Cubre el caso de que el
   usuario haya movido el cursor o hecho clic durante la corrección.
2. Se borra la selección con Retroceso y recién ahí se pega. Hay aplicaciones
   que conservan el resaltado pero **pegan como inserción**, lo que dejaría el
   texto original duplicado delante del nuevo.

Además, antes de cada `Ctrl+C` se **vacía el portapapeles**. Si no, copiar dos
veces el mismo texto no produce ningún cambio detectable y el corrector
concluiría erróneamente que no hay nada seleccionado.

### Pegar, comprobar, y si no, escribir

Hay aplicaciones que **leen bien el portapapeles pero no aceptan el `Ctrl+V`
sintético**: la ventana de redacción de Outlook es el caso. Ahí, pegar "funciona"
en el sentido de que no da error, pero no escribe nada.

Por eso, cuando la selección vino de UIA, el corrector **pega y después
comprueba** si el texto entró. Si no entró, escribe a mano con
`KEYEVENTF_UNICODE`, que sí responde en esas apps (y que además reemplaza la
selección directamente).

Sin esa comprobación, el corrector informaría éxito sin haber escrito nada, que
es peor que fallar.
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

Activa la corrección real. Requiere:

1. **Facturación activada** en tu proyecto de Google AI Studio.
2. Copiar `.env.example` a `.env` y pegar tu `GEMINI_API_KEY`.
3. `uv sync --extra ai`.

`iniciar.bat` detecta el `.env` y arranca solo en modo IA. Sin `.env`, arranca
en modo demo como hasta ahora.

### ⚠️ Por qué hace falta la facturación

Los [términos de Gemini API](https://ai.google.dev/gemini-api/terms) dicen que en
la cuota **gratuita** Google usa los textos enviados para mejorar sus productos
y que **revisores humanos pueden leerlos**. En la cuota **de pago** no se usan
para entrenar. Como el corrector se usa sobre correo, documentos y sistemas
empresariales, corresponde la cuota de pago.

### El prompt es conservador a propósito

Un corrector que reescribe es peor que uno que no corrige, porque el usuario
tiene que revisar cada cambio. El prompt pide explícitamente que **no** se
reformule, **no** se invente nada y que se respeten URLs, correos, SKU, rutas y
saltos de línea. Los ejemplos van en ambos sentidos: qué corregir y qué no.

Después del modelo, `guards.py` sigue haciendo su trabajo: si la respuesta
 came vacía, trae preámbulo, cambia las cifras o crece desmedidamente, **no se
escribe nada**.

### Medir el prompt antes de confiar en él

```powershell
uv run python src/main.py --bateria
```

Corre la batería de frases contra el modelo real **sin tocar ninguna pantalla**,
y muestra el antes y el después de cada una, cuántos coinciden exactamente y
cuántas rechazaron las guardas. También podés filtrar:

```powershell
uv run python src/main.py --bateria tilde
```

Las frases con `solo_puntuar` están ya bien escritas: si el modelo las cambia,
la batería lo marca como `TOCO UN TEXTO QUE YA ESTA BIEN`. Eso es una señal de
que el prompt se está saliendo del papel.

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
uv run python tests/smoke_hilo.py          # el ciclo completo desde un hilo de trabajo
uv run python tests/smoke_hotkey.py        # atajo global, sin ráfaga, cierre limpio
uv run python tests/smoke_privacidad.py    # logs sin texto, portapapeles intacto
uv run python tests/smoke_campo_entero.py  # el ultimo recurso y su guarda multilínea
uv run --with flet python tests/smoke_flet.py  # app Flutter real (requiere flet)
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