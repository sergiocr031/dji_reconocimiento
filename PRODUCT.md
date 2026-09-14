# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Equipos de rescate y bomberos que operan drones DJI en campo durante operaciones de búsqueda y rescate. El usuario primario trabaja bajo estrés operativo, a menudo al aire libre o en sala de mando, y necesita leer información crítica de un vistazo sin fricción cognitiva.

Audiencia secundaria: coordinadores o supervisores remotos que monitorean la operación desde sala de control.

## Product Purpose

Sistema de monitoreo aéreo en tiempo real que integra un dron DJI con detección de personas en peligro mediante IA (YOLOv8 pose estimation). El dron transmite video y telemetría a un backend Python (FastAPI) que analiza cada fotograma buscando posturas anormales (persona caída o acostada). Cuando se detecta, dispara una alerta sonora y visual con la ubicación GPS exacta al dashboard web y a la app Android del operador.

El éxito es: el equipo de rescate encuentra a la víctima más rápido porque el dron y la IA detectan antes de que el ojo humano lo haga.

## Positioning

El sistema cierra el ciclo completo sin intervención manual: dron DJI → app Android → backend IA → alerta en mapa con GPS. No requiere revisar el video manualmente; la detección es automática y empuja la alerta al operador.

## Operating Context

- Escenario principal: búsqueda y rescate en zonas de desastre (terremotos, inundaciones, derrumbes).
- El dashboard web se visualiza en desktop/laptop en sala de mando o en tablet en campo.
- El backend corre localmente o en un servidor accesible; el dron conecta desde una app Android sobre la misma red local o internet.
- El operador puede estar monitoreando múltiples parámetros simultáneamente: mapa, telemetría, feed de video, y log de alertas.
- El idioma de operación es español.
- Las decisiones de rescate son sensibles al tiempo: cada segundo de demora puede ser crítico.

## Capabilities and Constraints

- **Backend:** FastAPI + Python, YOLOv8n-pose, OpenCV. Detecta personas de pie, sentadas y acostadas (postura anormal = alerta).
- **App Android:** captura video del dron DJI (SDK MSDK v5), envía frames base64 + telemetría GPS al backend.
- **Dashboard web:** HTML/CSS/JS single-file, Leaflet (mapa), WebSocket para alertas en tiempo real.
- **Alertas:** WebSocket push → reproducción de sirena generada con Web Audio API (oscilador doble 620–1180 Hz, 2.8 s).
- **Datos:** lat/lon/altitud/velocidad/batería en tiempo real. Imágenes anotadas con bounding boxes incluidas en la alerta.
- **Sin nombre de marca confirmado:** se usará un nombre propuesto. Candidato de referencia: "SkyWatch SAR" (Search and Rescue).
- **Constraint técnica:** mapa usa Leaflet + OpenStreetMap, sin Carto ni tiles de pago obligatorios.

## Brand Commitments

Ningún activo de marca preexistente confirmado. El nombre actual en el código ("DJI Tactical Command") es un placeholder de desarrollo, no un nombre de marca aprobado.

El sistema debe proyectar seriedad operativa, confianza técnica y claridad bajo presión. No es un producto de consumo; es una herramienta de misión crítica.

## Evidence on Hand

- Backend funcional: `backend/main.py`, `backend/posture_detector.py`
- Dashboard web: `backend/static/index.html` (51 KB, single-file HTML/CSS/JS)
- Modelo de IA: `yolov8n-pose.pt` (6.8 MB)
- Script de simulación de vuelo: `backend/simulate_flight.py`
- App Android: `app/` (Kotlin, DJI MSDK v5)

Sin logo, sin guía de marca, sin testimonios o casos de uso documentados fuera del código.

## Product Principles

1. **Velocidad sobre decoración.** En una operación de rescate, la información debe leerse en menos de un segundo. Nada que no contribuya a esa lectura tiene derecho a estar en pantalla.
2. **La alerta no puede perderse.** El diseño debe garantizar que una alerta activa sea imposible de ignorar: visual + sonoro + GPS en mapa.
3. **Confianza técnica visible.** El sistema debe parecer tan robusto como lo es. Los operadores confían su toma de decisiones en él; la UI debe reflejar esa seriedad.
4. **Sin ruido, sin distracciones.** Modo oscuro operativo, jerarquía de datos clara, y solo la información que importa en la misión activa.
5. **El mapa es el centro.** La posición GPS de la víctima es el dato más valioso. El mapa y las alertas con coordenadas son el corazón de la experiencia.
