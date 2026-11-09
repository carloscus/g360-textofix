# Resumen de entrega — feat/mejoras-quick-wins (g360-textofix)

## Nivel
**B** (desarrollo de módulos): 7 mejoras de rendimiento y seguridad sobre el corrector.

---

## Cambios realizados

| Archivo | Qué se cambió | Item |
|---|---|---|
| `src/core/nvidia.py` | Cliente httpx persistente module-level con lock; temperature → 0.1; max_tokens dinámico (500–4000); import de `envolver_texto` movido a nivel módulo (resolver olor del reviewer); mensaje user envuelto en marcadores | 1, 2, 5 |
| `src/core/ai.py` | PROMPT: nueva regla #1 anti-inyección con `<<<TEXTO>>>`/`<<<FIN>>>`; funciones `MARCA_INICIO`, `MARCA_FIN`, `envolver_texto()`; variante agrega regla 11 | 5 |
| `src/core/engine.py` | `_motor_lock` module-level (serializa corregir/deshacer); cache LRU (`_cache_buscar`/`_cache_guardar`/`cache_vaciar`, clave `(etiqueta, modelo, texto)`, tope 32); llamada a `feedback.procesando()` en modo IA | 3, 6, 7 |
| `src/core/guards.py` | `extract_urls()`, `extract_correos()` al estilo `extract_digits`; guarda `"urls-correos-modificados"` en `validate()` | 4 |
| `src/core/feedback.py` | Nueva función `procesando()`; entrada `"procesando"` en SONIDOS / _BEEPS | 7 |
| `tools/generar_sonidos.py` | Entrada `"procesando"` para sintetizar WAV | 7 |
| `assets/sonidos/procesando.wav` | WAV generado (80 ms, 250 Hz) | 7 |
| `tests/conftest.py` | Fixture autouse que vacía el cache entre tests | 6 |
| `tests/test_cache_engine.py` | 8 tests: key composta, expulsión LRU, bypass evitando, None no cachea, mock no toca cache | 6 |
| `tests/test_engine_lock.py` | 3 tests: adquisición/liberación, serialización hilo-largo vs hilo-corto, aplicar_texto toma lock | 3 |
| `tests/test_nvidia.py` | Reescrito desde cero: 8 tests que ejercitan código real (keep-alive, temp 0.1, max_tokens min/max reales, envoltorio, timeout→respaldo, 401→no respaldo) | 1, 2, 5 |
| `tests/test_inyeccion.py` | 7 tests: envoltorio funciona, marcador no modifica contenido, promts declaran regla, variante numeración continúa, Gemini envuelve, marcadores compartidos AI/NIM | 5 |
| `tests/test_guards.py` | 8 tests nuevos: URL intacta/modificada, correo intacto/modificado, sin URLs no aplica, extractores conservan patrón | 4 |
| `tests/test_feedback.py` | 4 WAVs verificados; procesando respeta mute y usa fallback Beep | 7 |
| `tests/test_variantes.py` | Actualizado: tono esperado ahora incluye `procesando` antes de `sin` | 7 |
| `tests/test_ping.py` | Fix: fixture `monkeypatch` como parámetro explícito en test existente | — |
| `README.md` | Fila guardas URLs/correos; mención tono procesando en latencia; línea cache en Privacidad reestructurada | docs |

---

## Subagentes invocados

| Agente | Estado | Resultado |
|---|---|---|
| `architect` (ses_e467f49d9ffeK1GOO246HyTzzN) | **COMPLETADO** (parcial, se alcanzó límite de pasos) | Implementó los 7 items en src/. Dejó pendientes tests y README. |
| **Orquestador (yo)** | Continué en la misma sesión | Completé tests faltantes, corrigí tautologías, centralicé imports, ajusté README. |
| `reviewer` (ses_e42a105e6ffecdk9MBmu4PHX4P) | **COMPLETADO** | NECESITA-REVISION inicialmente; hallazgos MEDIO #2 (tautologías) y LEVEs fueron atendidos. Revisión de archivos centrales aprobada. |
| `security-auditor` | **COMPLETADO** | **APTO_CON_OBSERVACIONES**. Riesgo R1 (marcadores colisionan) medio-bajo, defensa en profundidad con guardas existentes; R2 (lock retenido durante red) bajo-documentado, comportamiento intencional. Sin riesgos bloqueantes. |

---

## Comando de verificación

```powershell
cd "C:\Users\ccusi\Documents\Proyect_Coder\G360-ecosystem\projects\.trees\g360-textofix\feat-mejoras-quick-wins"
uv sync --extra ai
uv run pytest
```

**Resultado:**
```
177 passed in 2.59s
```

---

## Correcciones aplicadas post-reviewer

1. **Tautologías max_tokens**: Los tests `test_max_tokens_minimo_para_texto_corto` y `test_max_tokens_limite_superior_4000` recalculaban la fórmula fuera de NIM. Ahora inyectan un `SpyClient` y verifican el JSON REAL enviado a la API.
2. **Import duplicado `envolver_texto`**: Movido a nivel módulo en `nvidia.py` (línea 39), eliminando el doble import local que el reviewer señaló como olor.
3. **Asserts redundantes en feedback**: Eliminadas comparaciones contra sí mismas en `test_procesando_es_distinto_y_mas_corto_que_ok`.
4. **README semántico**: La línea de Privacidad ya distingue claramente entre política de cache (memoria) y las mejoras de rendimiento asociadas.
5. **Marker colisión (R1 auditoría)**: No implementado — fuera de alcance "quick wins". Mitigación existente: guards (cifras, URLs, ratio, preámbulos) + naturaleza del flujo (texto seleccionado por el propio usuario). Se documentó como riesgo aceptado.

---

## Estado
**APROBADO**

Todos los criterios de aceptación cumplen:
- [x] 7 items implementados según spec
- [x] 177 tests passed, 0 skips agregados
- [x] Tests cubren keep-alive, temp 0.1, max_tokens boundaries reales, URLs/correos, anti-inyección, cache LRU, lock serialización, procesando mute
- [x] README actualizado mínimamente
- [x] Sin dependencias nuevas, sin variables de entorno nuevas
- [x] Comentarios en castellano sin acentos
- [x] Funciones pequeñas (<80 líneas)
- [x] Auditoría de seguridad: APTO_CON_OBSERVACIONES (riesgos documentados, no bloqueantes)
