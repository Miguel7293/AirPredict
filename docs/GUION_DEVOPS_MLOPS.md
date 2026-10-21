# Guion de exposición: DevOps y MLOps en 4 minutos

Versión concentrada del ciclo de automatización y del ciclo de vida del modelo. Un solo expositor puede cubrirla; practícala cronometrada. Deja abiertos de antemano: app pública en `/ready`, pestaña de Actions, y una terminal con el venv activo.

**Preparación:** ejecutar antes `python -m airepredict mlops-demo` y dejar `reports/mlops_demo.json` listo (o reejecutarlo en vivo si alcanza: tarda segundos).

---

## 0:00–0:45 · Arquitectura: un servicio que no escribe nada

**Mostrar:** `https://airpredict-4u3c.onrender.com/ready` → commit + versión del modelo.

**Decir:**

> «La app corre en Render gratis con un contenedor Docker. La decisión clave: **el servicio web nunca escribe estado ni entrena**. Solo consume copias completas del estado que GitHub Actions publica en la rama `runtime-state`. Actions es el único escritor, así que el servicio público no necesita ninguna credencial. `/ready` muestra el commit y el modelo exactos que está sirviendo ahora.»

---

## 0:45–2:00 · CI/CD: de git push a producción verificada

**Mostrar:** Actions → flujo **Build and deploy** de un push reciente a `main`.

**Decir:**

> «Cada push a main encadena dos jobs. Primero *validate*: 45 pruebas Python, smoke tests de cliente, y además **construye el contenedor y lo arranca**, comprobando que predice. No validamos el código: validamos el artefacto que va a producción.»

> «Luego *deploy*: publica la imagen en GHCR **etiquetada con el SHA del commit**, dispara el deploy hook de Render hacia ese commit y verifica durante hasta 15 minutos que `/ready` reporta exactamente ese SHA y que la API predice. Si la verificación falla, **se recupera automáticamente** el commit anterior sano. Y ojo: solo se puede recuperar un SHA que tuvo una entrega exitosa previa —no se restaura nada que no haya funcionado nunca—. Además, si alguien pusheó un commit más nuevo mientras tanto, el despliegue viejo se cancela solo. El auto-deploy de Render está apagado: nada llega a producción sin pasar por CI.»

---

## 2:00–3:30 · MLOps: registro inmutable y nueve puertas de calidad

**Mostrar:** terminal:

```bash
python -m airepredict registry-status
```

y `config/promotion_policy.json`.

**Decir:**

> «Los modelos viven en un registro SQLite inmutable: cada versión guarda el modelo, el código de features congelado, las dependencias y el hash SHA-256. La activación es transaccional —compare-and-swap—: solo cambia el modelo si el campeón sigue siendo el que se evaluó. Todo queda auditado en eventos.»

> «Un candidato solo sustituye al activo si pasa **nueve controles**: mínimo de ejemplos y días, cobertura, mejora del 2 % sobre el activo, ventaja sobre persistencia, límites de RMSE, sesgo y concentraciones altas, y una mejora estadísticamente consistente (bootstrap diario). Falla uno solo → el activo queda intacto. Contra data-leakage: la ventana de evaluación se **reserva y se consume** aunque falle el entrenamiento, y no se ajustan hiperparámetros contra esa ventana.»

---

## 3:30–4:00 · Demostración y cierre

**Mostrar:** salida de `mlops-demo` (o `reports/mlops_demo.json`):

```bash
python -m airepredict mlops-demo
```

**Decir:**

> «Esta demo corre en un registro **sandbox aislado** —no toca el de producción— y prueba el ciclo completo: primer entrenamiento **aceptado**, segundo **rechazado** por no mejorar, y **rollback** tras un fallo simulado. En producción, la ingesta corre cada hora, el reentrenamiento cada lunes y el monitor diario: si el activo degrada más de un 10 % contra persistencia y el anterior es claramente mejor, revierte automáticamente y bloquea el fallido. Todo con GitHub Actions, Docker y Render gratis: entrega verificada por commit, estado validado por hashes antes de servirse, y modelos que solo se activan pasando puertas de calidad.»

---

## Plan B rápido

| Fallo | Respuesta |
|---|---|
| Render dormido | Usar la app local; «limitación conocida del plan gratuito» |
| Actions lento/caído | Enseñar captura o el `mlops_demo.json` ya generado |
| `mlops-demo` falla | Enseñar el JSON previo y su lista de `events` |
| Piden más detalle | Apuntar a `docs/DEVOPS_MLOPS_ESTUDIO.md` (guía completa con 15 preguntas de repaso) |

---

## Preguntas rápidas del jurado

- **¿Qué impide que el servidor publique modelos?** No tiene credencial de escritura; solo descarga snapshots validados de Actions.
- **¿Qué pasa si el modelo nuevo falla tras activarse?** Smoke test post-activación → rollback inmediato.
- **¿Y si el candidato mejora pero el intervalo incluye cero?** Se rechaza: el control de bootstrap lo exige.
- **¿Recuperar app y recuperar el modelo es lo mismo?** No: commit+contenedor vs release del registro; cada uno con su verificación.
- **¿El modelo actual es de producción?** No: está marcado experimental, `promotion_policy_passed: false`.
