# g360-textofix

> Corrector de texto para Windows: atajo global, captura de la selección y reemplazo en el lugar.

Microherramienta del ecosistema G360. Seleccionás un texto en cualquier
aplicación, apretás `Ctrl+Shift+E` y el texto seleccionado se corrige y se
reemplaza donde estaba, sin perder el formato.

**Estado: Etapa 3 terminada.** Corrige **offline con Ollama local** por
defecto (sin cuota, sin red, el texto no sale de tu maquina) y cae a Gemini
por la nube cuando no hay Ollama. Vive en la bandeja del sistema, tiene
deshacer/rehacer, atajos configurables en caliente, y se empaqueta en un
`.exe` único de ~34 MB.

Los modelos que mejor corrigen el espanol peruano con el prompt conservador
se miden con `tools/comparar_modelos.py`. Por defecto corre
`llama3.2:3b` (el único que a velocidad utilizable en CPU).

---

## Tabla de contenidos

- [Cómo usar](#cómo-usar)
- [Atajos y bandeja](#atajos-y-bandeja)
- [Deshacer y rehacer](#deshacer-y-rehacer)
- [Qué funciona hoy](#qué-funciona-hoy)
- [Instalación](#instalación)
- [Distribución: el .exe](#distribución-el-exe)
- [Comandos](#comandos)
- [Configuración](#configuración)
- [Clave de la API y privacidad de la clave](#clave-de-la-api-y-privacidad-de-la-clave)
- [Cómo decide a quién corregir](#cómo-decide-a-quién-corregir)
- [Garantías de seguridad](#garantías-de-seguridad)
- [Corrección con Gemini y Ollama local](#corrección-con-gemini-y-ollama-local)
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

Se equivocó y querés volver atrás: `Ctrl + Shift + Z`. Lo querés reponer:
`Ctrl + Shift + R`.

---

## Atajos y bandeja

El corrector vive en la bandeja del sistema, no en una ventana. El icono es una
barra verde entre dos grises (el logo G360) y su menú es corto a propósito:

```
Activo · Modo IA
──────────────────────────────
Deshacer corrección            (gris si no hay nada)
Rehacer corrección             (gris si no hay nada)
──────────────────────────────
Cambiar atajo…
Configurar clave API…
Iniciar con Windows            ✓
──────────────────────────────
Salir
```

### Cambiar un atajo

`Cambiar atajo…` pide la acción y la combinación, valida el formato, **la
registra al momento** y la guarda en el perfil. No hace falta reiniciar.

Formato: `CTRL+SHIFT+E`, `ALT+F4`, `CTRL+1`, `WIN+E`, `CTRL+F5` — es decir,
`CTRL`, `ALT`, `SHIFT` o `WIN` más una letra, un dígito, `F1`–`F24` o alguna
tecla especial (`SPACE`, `ESC`, `ENTER`, `TAB`, `INSERT`, `DELETE`, `HOME`,
`END`, `PGUP`, `PGDN`).

Dos atajos iguales se rechazan: Windows no los acepta y quedarías sin saber
cuál de las dos acciones manda.

Los atajos por defecto y su equivalente en el archivo de perfil:

| Acción | Por defecto | Variable |
|---|---|---|
| Corregir | `Ctrl+Shift+E` | `hotkey_corregir` |
| Deshacer | `Ctrl+Shift+Z` | `hotkey_deshacer` |
| Rehacer | `Ctrl+Shift+R` | `hotkey_rehacer` |

### Iniciar con Windows

Se registra en `HKCU\...\Run`, es decir, **solo para el usuario que lo
instaló**, no para todos los que usan el equipo.

---

## Deshacer y rehacer

No se simula un `Ctrl+Z` de la aplicación: se guarda el par
`(original, corregido)` **en memoria** y se vuelve a escribir el original. Es
determinista en cualquier app, incluidas las que no responden a `Ctrl+Z`.

El búfer guarda **una sola corrección** —no es historial— y se pierde al
cerrar. Nunca toca disco.

**Deshacer no es ciego.** Hay dos reglas, y las dos evitan daño:

| Regla | Qué evita |
|---|---|
| Solo se deshace en la **misma aplicación** donde se corrigió | Corregiste en Flet, cambiaste a Word y apretaste deshacer: tono de error y **no se escribe nada**. |
| Se **invalida** si el usuario editó el texto después | Escribir el original encima de lo que el usuario puso sería peor que no deshacer. |

Si la escritura falla, el estado se revierte: el búfer no cree que aplicó algo
que no se escribió. En la bandeja, ambas opciones aparecen en gris cuando no
aplican.

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

### Opción A: el `.exe` (sin Python)

Descargá `dist/g360-textofix.exe` y ejecutalo. No requiere Python ni `uv`.

La primera vez te pide la clave de la API de Gemini. Podés pegarla desde la
consola con `Ctrl+V` o desde el menú de la bandeja (`Configurar clave API…`).

### Opción B: desde el código

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
uv run python src/main.py --modo ia
```

> **Nota sobre Python**: el proyecto no depende del Python del sistema. `uv`
> crea su propio entorno. Los lanzadores `py` y `pytest` del sistema apuntan a
> un Python 3.14 que no está instalado; por eso todo pasa por `uv run`.

### Empaquetar el `.exe`

```powershell
uv sync --extra pack
uvx pyinstaller textofix.spec --noconfirm
```

Sale un único archivo en `dist/g360-textofix.exe` (~26 MB) con el icono
incrustado. El `.spec` ya trae los `datas` (icono y batería de frases), así
que `--bateria` funciona también dentro del ejecutable.

Si el antivirus lo detecta como sospechoso (falso positivo por ser un `.exe`
de Python que simula teclas), Nuitka produce un binario más discreto:

```powershell
uv sync --extra pack
uv run python -m nuitka --onefile --windows-console-mode=disable `
    --windows-icon-from-ico=assets/g360-textofix.ico `
    --include-data-dir=assets=assets --include-data-dir=src/core=casos `
    --output-filename=g360-textofix.exe src/main.py
```

---

## Distribución: el `.exe`

**No se embebe ninguna clave.** Cada usuario introduce la suya la primera vez y
se guarda cifrada en su `%APPDATA%\g360-textofix\`. El ejecutable no lleva
secretos, así que puede repartirse libremente.

### Dónde guarda cada cosa

```
%APPDATA%\g360-textofix\
├── clave.dat     # la clave de Gemini, cifrada con DPAPI
└── config.json   # atajos, iniciar con Windows, activo/inactivo
```

**DPAPI** es la cifrado del propio Windows, atada a la cuenta del usuario. No
hay contraseña que recordar porque no existe contraseña: lo descifra Windows
solo para esa cuenta. Copiar `clave.dat` a otro equipo o a otra cuenta **no
sirve de nada**, y el archivo no contiene la clave en texto claro.

Para cambiar de clave, `Configurar clave API…` en la bandeja. Para borrarla del
todo, hay `borrar_clave_api()` en `src/core/perfil.py`.

### Uso en un solo equipo

Si solo lo usás vos, también podés dejar la clave en `.env` en la carpeta del
proyecto (git-ignorada). `iniciar.bat` la detecta y arranca en modo IA. El
almacenamiento DPAPI existe justamente para el `.exe`, que no tiene carpeta de
proyecto.

---

## Comandos

| Comando | Qué hace |
|---|---|
| `uv run python src/main.py` | Escucha los tres atajos, con la bandeja activa |
| `uv run python src/main.py --modo ia` | **Corrige de verdad** con Gemini |
| `uv run python src/main.py --once` | Una corrección sobre lo seleccionado y sale |
| `uv run python src/main.py --once --mock-transform wrap` | Envuelve el texto en `«»` para ver dónde se escribió |
| `uv run python src/main.py --bateria` | Corre la batería de frases, sin escribir nada |
| `uv run python src/main.py --bateria tilde --pausa 13` | Solo los casos `tilde`, con pausa para la cuota gratuita |
| `uv run python src/main.py --diagnostico` | Informa qué ventana está en primer plano y qué adaptador usaría |
| `uv run python src/main.py --sin-sonido` | Desactiva los tonos |
| `uv run python src/main.py --version` | Versión |
| `uv run python src/main.py -v` | Detalle en consola |

`--diagnostico` es el primer comando para usar si algo falla: dice si la
aplicación está bloqueada (UIPI) y qué adaptador corresponde.

---

## Configuración

Hay dos sitios, y cada uno para algo distinto.

### `%APPDATA%\g360-textofix\config.json` — lo que cambia el usuario

Es lo que escribe el menú de la bandeja. Se arranca leyendo `.env` y después
**este archivo manda**: lo que guardaste persiste entre sesiones.

| Llave | Por defecto | Para qué |
|---|---|---|
| `hotkey_corregir` | `CTRL+SHIFT+E` | Atajo de corrección |
| `hotkey_deshacer` | `CTRL+SHIFT+Z` | Atajo de deshacer |
| `hotkey_rehacer` | `CTRL+SHIFT+R` | Atajo de rehacer |
| `iniciar_con_windows` | `false` | Arranque automático |
| `activo` | `true` | Arranca activo o desactivado |

### `.env` — lo técnico, en la carpeta del proyecto

Opcional, y pensado sobre todo para desarrollo.

| Variable | Por defecto | Para qué |
|---|---|---|
| `GEMINI_API_KEY` | — | Clave de Gemini (solo si no hay clave DPAPI guardada) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Modelo a usar |
| `GEMINI_TIMEOUT_S` | `8` | Espera de la respuesta |
| `TEXTOFIX_SOUND` | `true` | Desactiva los tonos (pruebas automatizadas) |
| `TEXTOFIX_ENABLED` | `true` | Desactiva el corrector sin salir |
| `TEXTOFIX_VERBOSE` | `false` | Detalle en consola |
| `TEXTOFIX_CLIPBOARD_TIMEOUT_MS` | `400` | Espera al `Ctrl+C`. Subirlo ayuda en equipos lentos |

### Dónde busca la clave, en orden

1. **DPAPI** en `%APPDATA%\g360-textofix\clave.dat` — lo normal, y lo único que
   funciona con el `.exe`.
2. `GEMINI_API_KEY` del entorno o del `.env` — para desarrollo.

Guardá la clave desde la bandeja (`Configurar clave API…`) y deja de depender
del `.env`.

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

## Corrección con Gemini y Ollama local

Hay **dos proveedores** y el corrector elige solo el que tenga disponible:

| Proveedor | Cuándo se usa | Cuota | Red | Latencia |
|---|---|---|---|---|
| **Ollama local** (default) | Si Ollama está corriendo con un modelo descargado | 0 | No | 4–15 s |
| **Gemini** (fallback) | Si no hay Ollama, o si `PROVEEDOR_IA=gemini` | 5/min gratis | Sí | 2–5 s |

```powershell
# Ollama: corriendo en :11434, sin red, sin clave, sin cuota
ollama pull qwen3:8b          # mejor calidad para español
ollama pull gemma3:4b         # más liviano
ollama pull llama3.2:3b       # el más chico, rápido en CPU

# Para obligar uno:
$env:PROVEEDOR_IA = "gemini"    # o "ollama"
$env:OLLAMA_MODEL = "qwen3:8b"  # modelo local a usar
```

### Ollama local (la opción por defecto)

El `.exe` **no necesita clave ni red**. Si el usuario instaló Ollama y
descargó un modelo, corre offline para siempre. El texto **no sale de su
máquina**.

Para probar con un modelo local, primero hay que instalar Ollama
(descarga de [ollama.com](https://ollama.com), instalador estándar de
Windows) y descargar un modelo:

```powershell
ollama pull qwen3:8b
```

El modelo `qwen3:8b` (≈ 5 GB) es el que mejor responde al prompt conservador
del proyecto. El `gemma3:4b` (≈ 3.4 GB) corre más rápido y es suficiente
para correcciones cortas.

**Elegir modelo** con `tools/comparar_modelos.py`:

```powershell
uv run python tools/comparar_modelos.py          # todos, batería completa
uv run python tools/comparar_modelos.py qwen3    # solo qwen3
```

El resultado es una tabla por modelo: exactos, rechazados por la guarda y
latencia. Se usa para elegir entre los 4 sin probar uno a uno.

### Cuota gratuita y de pago: lo que hay que saber

La cuota **gratuita** de Gemini es cómoda para uso personal: unos 5 pedidos
por minuto, suficiente para corregir a mano mientras trabajás. Con
`--bateria` conviene poner `--pausa 13` para no quedarte sin cuota a mitad
de medida.

Los [términos de Gemini API](https://ai.google.dev/gemini-api/terms) dicen que
en la cuota gratuita Google usa los textos enviados para mejorar sus productos
y que **revisores humanos pueden leerlos**. En la de pago no se usan para
entrenar.

**Para uso personal, la gratuita alcanza.** Si el corrector se va a usar
sobre correo, documentos o sistemas de una empresa, **corresponde activar la
facturación**: no por el límite de pedidos, sino por los términos.

**Con Ollama local, no aplica nada de lo anterior**: el texto no sale de la
máquina, no hay cuota y no hay clave. Si usás Ollama, no necesitás
activar facturación.


### El idioma: español peruano

El prompt declara explícitamente **español peruano para texto de trabajo**. No
declarar la variedad dejaría que el modelo normalice hacia español de España,
que es justo lo que no queremos.

Y hay una regla explícita en contra de una costumbre común del modelo: **no
cambiar el vocabulario por variantes regionales**.

```
"computadora"  NO -> "ordenador"     (peruano correcto)
"combustible"  NO -> "gasolina"      (peruano correcto)
"celular"      NO -> "movil"         (peruano correcto)
"S/ 1,250.00"  NO -> "1250,00 €"     (no toques la moneda)
"12/05/2026"   NO -> "2026-05-12"    (no toques la fecha)
```

La batería tiene 6 casos dedicados a esto (`peru-*`). Si el modelo los cambia,
la batería lo marca, y eso es señal de que hay que reforzar el prompt.

El registro también se respeta: un correo formal no se informaliza.

### El prompt es conservador a propósito

Un corrector que reescribe es peor que uno que no corrige, porque el usuario
tiene que revisar cada cambio. El prompt pide explícitamente que **no** se
reformule, **no** se invente nada y que se respeten URLs, correos, SKU, rutas y
saltos de línea. Los ejemplos van en ambos sentidos: qué corregir y qué no.

Después del modelo, `guards.py` sigue haciendo su trabajo: si la respuesta
viene vacía, trae preámbulo, cambia las cifras o crece desmedidamente, **no se
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
├── textofix.spec               # PyInstaller: icono + datas
├── .env.example                # plantilla de configuración
├── assets/
│   └── g360-textofix.ico       # icono (generado por tools/)
├── src/
│   ├── main.py                 # CLI, bandeja, estado y los tres atajos
│   └── core/
│       ├── config.py           # configuración por entorno
│       ├── perfil.py           # %APPDATA%: clave DPAPI, config.json, autostart
│       ├── hotkey.py           # parser de atajos + escucha multi-atajo
│       ├── estado.py           # activo/inactivo + búfer de deshacer (puro)
│       ├── bandeja.py          # bandeja del sistema (pystray)
│       ├── engine.py           # ciclo: leer -> corregir -> validar -> escribir
│       ├── ai.py               # Gemini: prompt conservador, reintento en 429
│       ├── guards.py           # validaciones (puro, sin Windows)
│       ├── bateria.py          # ejecuta la batería contra el modelo
│       ├── casos.py            # las frases de prueba (viven aquí, no en tests)
│       ├── winapi.py           # Win32, SendInput, portapapeles, UIPI
│       ├── feedback.py         # tonos (winsound, stdlib)
│       ├── logsetup.py         # logging sin contenido
│       └── adapters/
│           ├── base.py         # contrato
│           ├── word.py         # Word por COM
│           ├── excel.py        # Excel por COM
│           └── generic.py      # UIA + portapapeles
├── tests/
│   ├── test_*.py               # tests puros (pytest)
│   └── smoke_*.py              # pruebas de humo reales (a mano)
└── tools/
    └── generar_icono.py        # genera assets/g360-textofix.ico
```

Las frases de prueba están en `src/core/casos.py` y **no** en `tests/`, para
que `--bateria` funcione también dentro del `.exe`: PyInstaller no empaqueta
la carpeta `tests/`.

---

## Testing

```powershell
:: Tests unitarios (rápidos, sin Windows salvo para los atajos)
uv run pytest

:: Pruebas de humo (abren ventanas reales y escriben en apps de verdad)
uv run python tests/smoke_win32_edit.py    # selección completa, parcial, al final, sin selección
uv run python tests/smoke_hilo.py          # el ciclo completo desde un hilo de trabajo
uv run python tests/smoke_hotkey.py        # 3 atajos, cambio en caliente, sin ráfaga, cierre limpio
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

### Lo que `smoke_hotkey.py` cubre de verdad

No comprueba que el parser devuelva lo esperado, que es fácil. Comprueba cosas
que solo se ven con `RegisterHotKey` real:

- los tres atajos se registran y cada pulsación dispara su acción;
- cuatro pulsaciones seguidas producen **una** ejecución, no cuatro;
- **cambiar un atajo en caliente**: el nuevo dispara sin reiniciar y el viejo
  queda libre para que otra app lo pueda registrar;
- cambiar a un atajo que ya usa otra acción se **rechaza**, y la acción
  conserva su combinación original;
- cerrar libera los atajos.

### Un aviso sobre `smoke_hotkey.py` en sesiones no interactivas

Si lo corrés desde un proceso con **integridad baja** (ciertos shells aislados,
servicios, algunas sesiones remotas), la pulsación sintética no llega: Windows
bloquea la inyección de teclas de un proceso de integridad baja hacia el
escritorio interactivo. El registro de los atajos funciona igual —solo
`RegisterHotKey`— pero el disparo no.

Se puede ver con:

```powershell
uv run python -c "from core.winapi import _current_integrity; print(_current_integrity())"
# 8192  -> Low: los atajos se registran, el disparo sintetico no llega
# 12288 -> Medium: todo normal
```

Desde una consola normal del usuario (integridad Medium) el test corre completo.

---

## Licencia

MIT.

---

## Familia G360

Microherramienta del [ecosistema G360](https://github.com/carloscus), una
familia de herramientas de apoyo CRM y gestión de datos en escritorio.